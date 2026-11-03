"""
byr_to_dng.py - Converts Tri-Cam .BYR (Bayer RAW12) containers to Adobe DNG v1.4 RAW files.

Builds on pidng with calibrated Sony IMX477 color matrices, white balance gains,
and embeds complete EXIF and GPS geotagging metadata directly into the output DNG.
"""

import os
import sys
import subprocess
from datetime import datetime, timezone
from typing import Optional, Union, Dict, Any
import numpy as np

from pidng.core import RAW2DNG, DNGTags, Tag
from pidng.defs import (
    CFAPattern,
    PhotometricInterpretation,
    CalibrationIlluminant,
    Orientation,
    DNGVersion,
    PreviewColorSpace,
)

from lib.byr_reader import BYRFile, BYRHeader, BAYER_PATTERNS

# Mapping from byr_format.h bayer_pattern enum to pidng CFAPattern
PIDNG_CFA_MAP = {
    0: CFAPattern.RGGB, # BAYER_RGGB
    1: CFAPattern.BGGR, # BAYER_BGGR
    2: CFAPattern.GRBG, # BAYER_GRBG
    3: CFAPattern.GBRG, # BAYER_GBRG
}

# Calibrated Sony IMX477 Color Correction Matrix (D65 Daylight)
# Adapted from Picamera2 / reference post-processing pipeline
IMX477_RGB_TO_XYZ = np.array([
    [0.4124564, 0.3575761, 0.1804375],
    [0.2126729, 0.7151522, 0.0721750],
    [0.0193339, 0.1191920, 0.9503041]
])

# Default sensor CCM (matches Picamera2 tuning for IMX477)
DEFAULT_SENSOR_CCM = np.array([
    [ 2.29, -1.09, -0.20],
    [-0.39,  1.65, -0.26],
    [-0.08, -0.63,  1.71]
])

COLOR_GAIN_DIV = 10000


def calculate_dng_color_matrices(wb_r: float = 2.1, wb_b: float = 1.8) -> tuple:
    """
    Computes ColorMatrix1 and AsShotNeutral for Adobe DNG based on IMX477 white balance gains.
    """
    gain_matrix = np.array([
        [wb_r, 0.0,  0.0 ],
        [0.0,  1.0,  0.0 ],
        [0.0,  0.0,  wb_b]
    ])

    # Compute inverse transform for ColorMatrix1
    try:
        combined = IMX477_RGB_TO_XYZ.dot(DEFAULT_SENSOR_CCM).dot(gain_matrix)
        ccm_inv = np.linalg.inv(combined)
    except np.linalg.LinAlgError:
        ccm_inv = np.eye(3)

    ccm1 = []
    for val in ccm_inv.flatten():
        ccm1.append((int(round(val * COLOR_GAIN_DIV)), COLOR_GAIN_DIV))

    gain_r_int = int(round(wb_r * COLOR_GAIN_DIV))
    gain_b_int = int(round(wb_b * COLOR_GAIN_DIV))
    as_shot_neutral = [
        [COLOR_GAIN_DIV, gain_r_int],
        [COLOR_GAIN_DIV, COLOR_GAIN_DIV],
        [COLOR_GAIN_DIV, gain_b_int]
    ]

    return ccm1, as_shot_neutral


def stamp_dng_exif_gps(dng_path: str, hdr: BYRHeader, baseline_exposure_ev: Optional[float] = None) -> bool:
    """
    Injects standard EXIF and GPS tags into the generated DNG file using exiftool.
    """
    cmd = ["exiftool", "-overwrite_original", "-q"]

    # 1. Geotagging
    lat = hdr.best_latitude
    lon = hdr.best_longitude
    alt = hdr.best_altitude

    if abs(lat) > 1e-6 or abs(lon) > 1e-6:
        lat_ref = "N" if lat >= 0 else "S"
        lon_ref = "E" if lon >= 0 else "W"
        cmd.extend([
            f"-GPSLatitude={abs(lat):.8f}",
            f"-GPSLatitudeRef={lat_ref}",
            f"-GPSLongitude={abs(lon):.8f}",
            f"-GPSLongitudeRef={lon_ref}",
            f"-GPSAltitude={alt:.3f}",
            "-GPSAltitudeRef=0", # Above Sea Level
        ])

    # 2. Timing
    dt = hdr.datetime_utc
    if dt:
        date_str = dt.strftime("%Y:%m:%d %H:%M:%S")
        date_stamp = dt.strftime("%Y:%m:%d")
        time_stamp = dt.strftime("%H:%M:%S")
        subsec = f"{dt.microsecond // 1000:03d}"
        cmd.extend([
            f"-DateTimeOriginal={date_str}",
            f"-CreateDate={date_str}",
            f"-ModifyDate={date_str}",
            f"-SubSecTimeOriginal={subsec}",
            f"-GPSDateStamp={date_stamp}",
            f"-GPSTimeStamp={time_stamp}",
        ])

    # 3. Hardware & Lens Identity
    cmd.extend([
        f"-Make=Sony",
        f"-Model=IMX477",
        f"-CameraSerialNumber=0x{hdr.bcm_cpu_serial:016X}",
        f"-FocalLength={hdr.lens_focal_len_mm:.1f}",
        f"-LensModel=Calibrated {hdr.lens_focal_len_mm:.1f}mm",
        f"-ImageDescription=Tri-Cam Photogrammetry ({hdr.node_role}, Seq: {hdr.seq})",
        f"-Artist=GCC X500 Tri-Cam",
    ])

    # 4. Exposure & ISO
    if hdr.exposure_time_us > 0:
        exp_sec = hdr.exposure_time_us * 1e-6
        cmd.append(f"-ExposureTime={exp_sec:.6f}")
    if hdr.iso_equivalent > 0:
        cmd.append(f"-ISO={hdr.iso_equivalent}")
    if baseline_exposure_ev is not None:
        cmd.append(f"-ExposureBiasValue={baseline_exposure_ev:+.2f}")

    cmd.append(dng_path)

    try:
        ret = subprocess.run(cmd, capture_output=True, text=True, timeout=15.0)
        return ret.returncode == 0
    except Exception as e:
        print(f"Warning: Failed to stamp EXIF via exiftool: {e}", file=sys.stderr)
        return False


def convert_byr_to_dng(byr_input: Union[str, BYRFile], 
                       output_dng_path: str, 
                       compress: bool = False,
                       cfa_override: Optional[str] = None,
                       baseline_exposure_ev: Optional[float] = None) -> str:
    """
    Converts a .byr container into an Adobe DNG v1.4 RAW image.

    Args:
        byr_input: File path string or BYRFile instance.
        output_dng_path: Target .dng destination file path.
        compress: Whether to apply lossless JPEG compression (LJ92) via pidng.
        cfa_override: Optional manual override for Bayer pattern ('RGGB', 'BGGR', etc.).
                      If None, strictly reads bayer_pattern from the .byr container header.
        baseline_exposure_ev: Optional non-destructive EV compensation offset.

    Returns:
        The output DNG file path.
    """
    if isinstance(byr_input, str):
        byr = BYRFile(byr_input)
    else:
        byr = byr_input

    hdr = byr.header
    pixels = byr.read_pixels()

    # DNG Dimensions and bit depth
    height, width = pixels.shape
    bpp = hdr.bit_depth # 12-bit

    # Black level: 256 DN for IMX477 12-bit ADC
    black_levels = [256, 256, 256, 256]
    white_level = (1 << bpp) - 1 # 4095

    # CFA pattern: Strictly read from .BYR container header unless explicitly overridden
    if cfa_override is not None:
        cfa_map = {"RGGB": CFAPattern.RGGB, "BGGR": CFAPattern.BGGR, "GRBG": CFAPattern.GRBG, "GBRG": CFAPattern.GBRG}
        cfa_key = cfa_override.upper()
        if cfa_key not in cfa_map:
            raise ValueError(f"Unknown CFA override '{cfa_override}'. Valid options: {list(cfa_map.keys())}")
        cfa_pattern = cfa_map[cfa_key]
    else:
        if hdr.bayer_pattern not in PIDNG_CFA_MAP:
            raise ValueError(
                f"Missing or invalid Bayer pattern enum {hdr.bayer_pattern} in .byr header for '{byr.file_path}'. "
                f"Cannot reconstruct DNG without valid Bayer pixel info (0=RGGB, 1=BGGR, 2=GRBG, 3=GBRG)."
            )
        cfa_pattern = PIDNG_CFA_MAP[hdr.bayer_pattern]

    # Color Matrices
    ccm1, as_shot_neutral = calculate_dng_color_matrices(hdr.wb_gain_r, hdr.wb_gain_b)
    camera_calibration = [
        [1, 1], [0, 1], [0, 1],
        [0, 1], [1, 1], [0, 1],
        [0, 1], [0, 1], [1, 1]
    ]

    # Baseline exposure
    exposure_time_s = (hdr.exposure_time_us * 1e-6) if hdr.exposure_time_us > 0 else 0.001
    exp_frac = 1.0 / exposure_time_s if exposure_time_s > 0 else 1000.0
    exp_rational = [1, int(round(exp_frac))]
    focal_rational = [int(round(hdr.lens_focal_len_mm * 10)), 10]

    # Sensor area for Sony IMX477 (6.287mm x 4.712mm)
    sensor_image_area = (6.287, 4.712)
    focal_plane_x_res = [int(round(width * 10 * 1000)), int(round(sensor_image_area[0] * 1000))]
    focal_plane_y_res = [int(round(height * 10 * 1000)), int(round(sensor_image_area[1] * 1000))]

    dt = hdr.datetime_utc or datetime.now(timezone.utc)
    date_str = dt.strftime("%Y:%m:%d %H:%M:%S")
    subsec_str = f"{dt.microsecond // 1000:03d}"

    # Build DNG Tags
    tags = DNGTags()
    tags.set(Tag.ImageWidth, width)
    tags.set(Tag.ImageLength, height)
    tags.set(Tag.SamplesPerPixel, 1)
    tags.set(Tag.BitsPerSample, bpp)
    tags.set(Tag.WhiteLevel, white_level)
    tags.set(Tag.Orientation, Orientation.Horizontal)

    tags.set(Tag.Make, "Sony")
    tags.set(Tag.Model, "IMX477")
    tags.set(Tag.UniqueCameraModel, f"Sony IMX477 ({hdr.node_role})")
    tags.set(Tag.CameraSerialNumber, f"0x{hdr.bcm_cpu_serial:016X}")
    tags.set(Tag.RawDataUniqueID, f"{hdr.seq:09d}_{hdr.node_role}_{hdr.task_uuid_hex[:8]}".encode("ascii"))

    tags.set(Tag.DateTime, date_str)
    tags.set(Tag.SubsecTime, subsec_str)
    tags.set(Tag.DateTimeOriginal, date_str)
    tags.set(Tag.SubsecTimeOriginal, subsec_str)

    tags.set(Tag.ExposureTime, [exp_rational])
    tags.set(Tag.PhotographicSensitivity, [hdr.iso_equivalent])
    tags.set(Tag.FocalLength, [focal_rational])
    tags.set(Tag.FocalPlaneXResolution, [focal_plane_x_res])
    tags.set(Tag.FocalPlaneYResolution, [focal_plane_y_res])

    # Bayer CFA & Color Tags
    tags.set(Tag.PhotometricInterpretation, PhotometricInterpretation.Color_Filter_Array)
    tags.set(Tag.CFARepeatPatternDim, [2, 2])
    tags.set(Tag.CFAPattern, cfa_pattern)
    tags.set(Tag.BlackLevelRepeatDim, [2, 2])
    tags.set(Tag.BlackLevel, black_levels)
    tags.set(Tag.ColorMatrix1, ccm1)
    tags.set(Tag.CameraCalibration1, camera_calibration)
    tags.set(Tag.CameraCalibration2, camera_calibration)
    tags.set(Tag.CalibrationIlluminant1, CalibrationIlluminant.D65)
    tags.set(Tag.AsShotNeutral, as_shot_neutral)
    if baseline_exposure_ev is not None:
        base_ev_int = int(round(baseline_exposure_ev * 100))
        tags.set(Tag.BaselineExposure, [[base_ev_int, 100]])
    else:
        tags.set(Tag.BaselineExposure, [[1, 1]])

    tags.set(Tag.DNGVersion, DNGVersion.V1_4)
    tags.set(Tag.DNGBackwardVersion, DNGVersion.V1_2)
    tags.set(Tag.PreviewColorSpace, PreviewColorSpace.sRGB)

    # Convert to DNG file
    os.makedirs(os.path.dirname(os.path.abspath(output_dng_path)), exist_ok=True)
    r = RAW2DNG()
    r.options(tags, path="", compress=compress)
    r.convert(pixels, filename=output_dng_path)

    # Stamp EXIF and GPS tags
    stamp_dng_exif_gps(output_dng_path, hdr, baseline_exposure_ev=baseline_exposure_ev)

    return output_dng_path
