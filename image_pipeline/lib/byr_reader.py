"""
byr_reader.py - Parser and unpacker for Tri-Cam .BYR (Bayer RAW12) containers.

Binary Layout (4,096-byte header + 18,495,360-byte payload = 18,501,632 bytes total):
- Section 1 (0..15): Container Format & Dimensions ("BYR1", 4056x3040, RAW12 packed)
- Section 2 (16..155): Project & Sortie UUID (16-byte binary & 36-char string)
- Section 3 (160..287): Camera Hardware Identity & Node Role (Nadir/ObliqueRt/ObliqueFwd)
- Section 4 (288..351): GNSS PPK Timing Reference (seq, week, tow_ms, sub_ns, unix_utc_us)
- Section 5 (352..415): Real-Time Estimated GNSS Position (lat, lon, alt_msl, accuracies)
- Section 6 (416..543): Pre-Allocated PPK Post-Processed Geotagging
- Section 7 (544..607): Optional / Forward-Compatible Exposure & Calibration
"""

import os
import struct
import ctypes
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Tuple, BinaryIO, Union
import numpy as np

# Header Constants matching byr_format.h
BYR_MAGIC = b"BYR1"
BYR_HEADER_SIZE_BYTES = 4096
BYR_IMAGE_WIDTH_PX = 4056
BYR_IMAGE_HEIGHT_PX = 3040
BYR_RAW_PIXEL_BYTES = 18495360      # 4056 * 3040 * 1.5
BYR_PAYLOAD_ALIGNED_BYTES = 18497536 # 4KB flash-aligned
BYR_TOTAL_FILE_BYTES = 18501632

BYR_COMPRESSION_NONE = 0
BYR_COMPRESSION_BYTEPLANE_LZ4 = 1
BYR_COMPRESSION_DPCM_RICE = 2

# Load C decompressor shared library if available
_libdpcm = None
try:
    _so_path = os.path.join(os.path.dirname(__file__), "libdpcm.so")
    if os.path.isfile(_so_path):
        _libdpcm = ctypes.CDLL(_so_path)
        _libdpcm.decompress_dpcm_rice.argtypes = [
            ctypes.c_char_p, ctypes.c_size_t,
            ctypes.c_char_p, ctypes.c_size_t
        ]
        _libdpcm.decompress_dpcm_rice.restype = ctypes.c_size_t
except Exception as _e:
    _libdpcm = None

def decompress_dpcm_payload(comp_bytes: bytes) -> bytes:
    """
    Decompresses a Bayer DPCM + Rice bitstream back to unpadded RAW12 (18,495,360 bytes).
    """
    if _libdpcm is not None:
        raw_out = ctypes.create_string_buffer(BYR_RAW_PIXEL_BYTES)
        ret = _libdpcm.decompress_dpcm_rice(comp_bytes, len(comp_bytes), raw_out, BYR_RAW_PIXEL_BYTES)
        if ret == BYR_RAW_PIXEL_BYTES:
            return raw_out.raw
        raise RuntimeError(f"DPCM C decompression failed (returned {ret})")
    raise RuntimeError("libdpcm.so not found for DPCM-Rice decompression")

BAYER_PATTERNS = {
    0: "RGGB",
    1: "BGGR",
    2: "GRBG",
    3: "GBRG",
}


@dataclass
class BYRHeader:
    # Section 1: Container format
    magic: str
    header_version: int
    header_size: int
    width: int
    height: int
    bayer_pattern: int
    bit_depth: int

    # Section 2: Project & Sortie UUID
    task_uuid: bytes
    task_uuid_hex: str
    dronetm_project_num: int
    dronetm_task_num: int
    dronetm_project_name: str
    dronetm_task_name: str

    # Section 3: Camera hardware identity
    node_id: int
    node_role: str
    bcm_cpu_serial: int
    sd_card_cid: bytes
    sensor_model: str
    lens_focal_len_mm: float
    sd_card_csd: bytes
    sd_card_name: str
    sd_manfid: int
    sd_oemid: int
    sd_date: str
    sd_benchmark_mb_s: float
    sd_perf_tier: int

    # Section 4: GNSS PPK timing reference
    seq: int
    gps_week: int
    gps_tow_ms: int
    sub_ns: int
    unix_utc_us: int
    timebase_lock: int

    # Section 5: Real-time estimated GNSS position
    rt_latitude: float
    rt_longitude: float
    rt_altitude_msl: float
    rt_h_acc_m: float
    rt_v_acc_m: float
    rt_fix_type: int

    # Section 6: Pre-allocated PPK geotagging
    ppk_latitude: float
    ppk_longitude: float
    ppk_altitude_ellipsoid: float
    ppk_h_acc_m: float
    ppk_v_acc_m: float
    ppk_fix_status: int

    # Section 7: Compression & Radiometric Sensor Telemetry (Offsets 544..671)
    compression_codec: int = 0
    compression_flags: int = 0
    payload_compressed_bytes: int = 18495360
    line_stride_bytes: int = 6084
    exposure_time_us: int = 1000
    analogue_gain: float = 1.0
    digital_gain: float = 1.0
    iso_equivalent: int = 100
    sensor_temp_deg_c: int = 40
    sensor_hw_frame_count: int = 0
    sensor_model_id: int = 0x0477
    sensor_silicon_rev: int = 1
    sensor_telemetry_flags: int = 0
    camera_serial_num: str = ""
    wb_gain_r: float = 2.1
    wb_gain_b: float = 1.8
    line_length_pck: int = 4056
    frame_length_lines: int = 3040

    @property
    def bayer_name(self) -> str:
        if self.bayer_pattern not in BAYER_PATTERNS:
            raise ValueError(
                f"Missing or invalid Bayer pattern enum {self.bayer_pattern} in header. "
                f"Valid values: 0=RGGB, 1=BGGR, 2=GRBG, 3=GBRG."
            )
        return BAYER_PATTERNS[self.bayer_pattern]

    @property
    def datetime_utc(self) -> Optional[datetime]:
        if self.unix_utc_us > 0:
            return datetime.fromtimestamp(self.unix_utc_us / 1_000_000.0, tz=timezone.utc)
        elif self.gps_week > 0 and self.gps_tow_ms > 0:
            gps_epoch = datetime(1980, 1, 6, tzinfo=timezone.utc)
            total_sec = (self.gps_week * 7 * 86400) + (self.gps_tow_ms / 1000.0) + (self.sub_ns / 1_000_000_000.0)
            # Subtract 18 GPS leap seconds to align with UTC
            total_sec -= 18.0
            return datetime.fromtimestamp(gps_epoch.timestamp() + total_sec, tz=timezone.utc)
        return None

    @property
    def has_ppk(self) -> bool:
        return (self.ppk_fix_status > 0 and 
                (abs(self.ppk_latitude) > 1e-6 or abs(self.ppk_longitude) > 1e-6))

    @property
    def best_latitude(self) -> float:
        return self.ppk_latitude if self.has_ppk else self.rt_latitude

    @property
    def best_longitude(self) -> float:
        return self.ppk_longitude if self.has_ppk else self.rt_longitude

    @property
    def best_altitude(self) -> float:
        return self.ppk_altitude_ellipsoid if self.has_ppk else float(self.rt_altitude_msl)

    @classmethod
    def from_bytes(cls, buf: bytes) -> "BYRHeader":
        if len(buf) < BYR_HEADER_SIZE_BYTES:
            raise ValueError(f"Header buffer too short: {len(buf)} bytes, expected {BYR_HEADER_SIZE_BYTES}")

        # Section 1 (0..15)
        magic_bytes = buf[0:4]
        if magic_bytes != BYR_MAGIC:
            raise ValueError(f"Invalid BYR magic: {magic_bytes}, expected {BYR_MAGIC}")
        hdr_version, hdr_size, width, height, bayer, bit_depth = struct.unpack("<HHHHBB", buf[4:14])
        if bayer not in BAYER_PATTERNS:
            raise ValueError(
                f"Missing or invalid Bayer pattern enum {bayer} in .byr header (offset 12). "
                f"Expected 0=RGGB, 1=BGGR, 2=GRBG, 3=GBRG."
            )

        # Section 2 (16..155)
        task_uuid = buf[16:32]
        task_uuid_hex = buf[32:68].decode("ascii", errors="replace").rstrip("\x00")
        dtm_proj_num, dtm_task_num = struct.unpack("<II", buf[68:76])
        dtm_proj_name = buf[76:116].decode("ascii", errors="replace").rstrip("\x00")
        dtm_task_name = buf[116:156].decode("ascii", errors="replace").rstrip("\x00")

        # Section 3 (160..287)
        node_id = buf[160]
        node_role = buf[161:176].decode("ascii", errors="replace").rstrip("\x00")
        bcm_cpu_serial = struct.unpack("<Q", buf[176:184])[0]
        sd_cid = buf[184:200]
        sensor_model = buf[200:216].decode("ascii", errors="replace").rstrip("\x00")
        lens_focal_len = struct.unpack("<f", buf[216:220])[0]
        sd_csd = buf[220:236]
        sd_name = buf[236:244].decode("ascii", errors="replace").rstrip("\x00")
        sd_manfid, sd_oemid = struct.unpack("<HH", buf[244:248])
        sd_date = buf[248:256].decode("ascii", errors="replace").rstrip("\x00")
        sd_bench_mb_s = struct.unpack("<f", buf[256:260])[0]
        sd_tier = buf[260]

        # Section 4 (288..351)
        seq, gps_week, gps_tow_ms, sub_ns, unix_utc_us, timebase_lock = struct.unpack(
            "<IHIIQB", buf[288:311]
        )

        # Section 5 (352..415)
        rt_lat, rt_lon, rt_alt, rt_h_acc, rt_v_acc, rt_fix = struct.unpack(
            "<ddfffB", buf[352:381]
        )

        # Section 6 (416..543)
        ppk_lat, ppk_lon, ppk_alt, ppk_h_acc, ppk_v_acc, ppk_status = struct.unpack(
            "<dddffB", buf[416:449]
        )

        # Section 7: Compression & Radiometric Sensor Telemetry (544..671)
        comp_codec, comp_flags = struct.unpack("<BB", buf[544:546])
        comp_bytes, stride_bytes, exp_us, ana_gain, dig_gain, iso_eq, sens_temp, hw_cnt, model_id, sil_rev, telem_flags = struct.unpack(
            "<IIIf f H b B H B B", buf[548:576]
        )
        cam_serial = buf[576:600].decode("ascii", errors="replace").rstrip("\x00")
        wb_r, wb_b, line_len_pck, frame_len_lines = struct.unpack(
            "<ffHH", buf[600:612]
        )

        # Sanity check values
        if stride_bytes == 0:
            stride_bytes = 6084
        if exp_us == 0 or exp_us > 10_000_000:
            exp_us = 1000 # default 1/1000s
        if ana_gain <= 0.0 or ana_gain > 100.0 or np.isnan(ana_gain):
            ana_gain = 1.0
        if dig_gain <= 0.0 or dig_gain > 100.0 or np.isnan(dig_gain):
            dig_gain = 1.0
        if iso_eq < 50 or iso_eq > 51200:
            iso_eq = int(round(ana_gain * dig_gain * 100.0))
        if wb_r <= 0.1 or wb_r > 10.0 or np.isnan(wb_r):
            wb_r = 2.1 # IMX477 daylight red gain
        if wb_b <= 0.1 or wb_b > 10.0 or np.isnan(wb_b):
            wb_b = 1.8 # IMX477 daylight blue gain
        if line_len_pck == 0:
            line_len_pck = 4056
        if frame_len_lines == 0:
            frame_len_lines = 3040

        return cls(
            magic=magic_bytes.decode("ascii"),
            header_version=hdr_version,
            header_size=hdr_size,
            width=width,
            height=height,
            bayer_pattern=bayer,
            bit_depth=bit_depth,
            task_uuid=task_uuid,
            task_uuid_hex=task_uuid_hex,
            dronetm_project_num=dtm_proj_num,
            dronetm_task_num=dtm_task_num,
            dronetm_project_name=dtm_proj_name,
            dronetm_task_name=dtm_task_name,
            node_id=node_id,
            node_role=node_role,
            bcm_cpu_serial=bcm_cpu_serial,
            sd_card_cid=sd_cid,
            sensor_model=sensor_model,
            lens_focal_len_mm=lens_focal_len,
            sd_card_csd=sd_csd,
            sd_card_name=sd_name,
            sd_manfid=sd_manfid,
            sd_oemid=sd_oemid,
            sd_date=sd_date,
            sd_benchmark_mb_s=sd_bench_mb_s,
            sd_perf_tier=sd_tier,
            seq=seq,
            gps_week=gps_week,
            gps_tow_ms=gps_tow_ms,
            sub_ns=sub_ns,
            unix_utc_us=unix_utc_us,
            timebase_lock=timebase_lock,
            rt_latitude=rt_lat,
            rt_longitude=rt_lon,
            rt_altitude_msl=rt_alt,
            rt_h_acc_m=rt_h_acc,
            rt_v_acc_m=rt_v_acc,
            rt_fix_type=rt_fix,
            ppk_latitude=ppk_lat,
            ppk_longitude=ppk_lon,
            ppk_altitude_ellipsoid=ppk_alt,
            ppk_h_acc_m=ppk_h_acc,
            ppk_v_acc_m=ppk_v_acc,
            ppk_fix_status=ppk_status,
            compression_codec=comp_codec,
            compression_flags=comp_flags,
            payload_compressed_bytes=comp_bytes,
            line_stride_bytes=stride_bytes,
            exposure_time_us=exp_us,
            analogue_gain=ana_gain,
            digital_gain=dig_gain,
            iso_equivalent=iso_eq,
            sensor_temp_deg_c=sens_temp,
            sensor_hw_frame_count=hw_cnt,
            sensor_model_id=model_id,
            sensor_silicon_rev=sil_rev,
            sensor_telemetry_flags=telem_flags,
            camera_serial_num=cam_serial,
            wb_gain_r=wb_r,
            wb_gain_b=wb_b,
            line_length_pck=line_len_pck,
            frame_length_lines=frame_len_lines,
        )


def unpack_raw12_unicam(raw_bytes: bytes, 
                        width: int = BYR_IMAGE_WIDTH_PX, 
                        height: int = BYR_IMAGE_HEIGHT_PX,
                        stride: Optional[int] = None) -> np.ndarray:
    """
    Vectorized unpacker for Unicam pRCC (V4L2_PIX_FMT_SRGGB12P) packed Bayer data.
    
    Hardware alignment:
      Width = 4056 px (2028 pairs of pixels per row).
      Row bytes unpadded = 2028 * 3 = 6084 bytes.
      Raspberry Pi Unicam aligns scanlines to a 32-byte multiple:
        (6084 + 31) & ~31 = 6112 bytes per scanline.
      Every 3 bytes [B0, B1, B2] encode 2 pixels:
        P0 = (B0 << 4) | (B2 & 0x0F)
        P1 = (B1 << 4) | ((B2 >> 4) & 0x0F)
        
    Returns:
      np.ndarray of shape (height, width) with dtype uint16, values in [0, 4095].
    """
    pairs_per_row = width // 2
    row_bytes_unpadded = pairs_per_row * 3 # 6084 bytes

    # Determine row stride
    if stride is None:
        unicam_stride = (row_bytes_unpadded + 31) & ~31 # e.g. 6112 for 4056 px
        total_len = len(raw_bytes)
        # Check if buffer has Unicam 32-byte line alignment
        if unicam_stride > row_bytes_unpadded and (total_len // unicam_stride) >= max(1, height - 30):
            stride = unicam_stride
        else:
            stride = row_bytes_unpadded

    if stride < row_bytes_unpadded:
        raise ValueError(f"Stride {stride} cannot be smaller than unpadded row {row_bytes_unpadded}")

    available_rows = min(height, len(raw_bytes) // stride)
    if available_rows <= 0:
        raise ValueError("Payload buffer too short to extract even 1 full row")

    # Extract 2D array of (available_rows, stride) and trim line padding to (available_rows, row_bytes_unpadded)
    data = np.frombuffer(raw_bytes[: available_rows * stride], dtype=np.uint8).reshape((available_rows, stride))
    data_unpadded = data[:, :row_bytes_unpadded]

    # If the buffer truncated the last few rows due to 18.5 MB payload clamp,
    # pad cleanly by tiling the last 2 scanlines to preserve 2x2 Bayer CFA grid alignment
    if available_rows < height:
        full_data = np.empty((height, row_bytes_unpadded), dtype=np.uint8)
        full_data[:available_rows] = data_unpadded
        needed = height - available_rows
        tile_count = (needed + 1) // 2
        repeated = np.tile(data_unpadded[-2:], (tile_count, 1))[:needed]
        full_data[available_rows:] = repeated
    else:
        full_data = data_unpadded

    # Reshape to (height, pairs_per_row, 3)
    data_3d = full_data.reshape((height, pairs_per_row, 3)).astype(np.uint16)

    b0 = data_3d[:, :, 0]
    b1 = data_3d[:, :, 1]
    b2 = data_3d[:, :, 2]

    p0 = (b0 << 4) | (b2 & 0x0F)
    p1 = (b1 << 4) | ((b2 >> 4) & 0x0F)

    # Interleave into output array (height, width)
    pixels = np.empty((height, width), dtype=np.uint16)
    pixels[:, 0::2] = p0
    pixels[:, 1::2] = p1

    return pixels



class BYRFile:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self._header: Optional[BYRHeader] = None
        self._pixels: Optional[np.ndarray] = None

    @property
    def header(self) -> BYRHeader:
        if self._header is None:
            self._header = self.read_header()
        return self._header

    def read_header(self) -> BYRHeader:
        with open(self.file_path, "rb") as f:
            header_buf = f.read(BYR_HEADER_SIZE_BYTES)
        return BYRHeader.from_bytes(header_buf)

    def read_pixels(self) -> np.ndarray:
        if self._pixels is not None:
            return self._pixels

        hdr = self.header
        with open(self.file_path, "rb") as f:
            f.seek(BYR_HEADER_SIZE_BYTES)
            if hdr.compression_codec == BYR_COMPRESSION_DPCM_RICE:
                comp_len = hdr.payload_compressed_bytes
                comp_payload = f.read(comp_len)
                payload = decompress_dpcm_payload(comp_payload)
            else:
                payload = f.read(BYR_RAW_PIXEL_BYTES)

        self._pixels = unpack_raw12_unicam(payload, hdr.width, hdr.height, stride=hdr.line_stride_bytes)
        return self._pixels

    def write_ppk_geotags(self, lat: float, lon: float, alt_ellipsoid: float, 
                           h_acc: float = 0.02, v_acc: float = 0.05, 
                           fix_status: int = 1) -> None:
        """
        Updates Section 6 (Pre-Allocated PPK Geotagging) in-place in the 4KB header.
        Does not rewrite or touch the 18.5 MB pixel payload!
        """
        ppk_bytes = struct.pack("<dddffB", lat, lon, alt_ellipsoid, h_acc, v_acc, fix_status)
        with open(self.file_path, "r+b") as f:
            f.seek(416) # Section 6 offset
            f.write(ppk_bytes)

        # Invalidate cached header
        self._header = None
