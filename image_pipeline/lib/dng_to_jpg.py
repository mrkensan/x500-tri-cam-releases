"""
dng_to_jpg.py - Converts Adobe DNG RAW images into full-resolution, high-quality JPEGs.

Uses rawpy (LibRaw) for AHD demosaicing, camera white balance, and sRGB color mapping,
followed by full EXIF and GPS geotagging metadata propagation via exiftool.
"""

import os
import sys
import subprocess
from typing import Optional, Union
import rawpy
from PIL import Image


def convert_dng_to_jpg(dng_path: str, 
                       output_jpg_path: str, 
                       quality: int = 95,
                       subsampling: int = 0,
                       wb_mode: str = "auto",
                       exp_shift: float = 1.0,
                       exp_preserve_highlights: float = 1.0,
                       denoise: bool = False,
                       contrast_boost: float = 1.0) -> str:
    """
    Renders an Adobe DNG RAW image to a high-quality JPEG and propagates all metadata.

    Args:
        dng_path: Path to the source Adobe DNG file.
        output_jpg_path: Destination path for the resulting JPEG.
        quality: JPEG compression quality (default: 95).
        subsampling: Chroma subsampling (0 = 4:4:4 for highest edge detail in photogrammetry).
        wb_mode: 'camera' to use embedded AsShotNeutral / camera WB, or 'auto' for LibRaw AWB.
        exp_shift: Exposure adjustment multiplier (e.g. 0.5 = -1 EV stop, 0.25 = -2 EV stops, 1.0 = linear).
        exp_preserve_highlights: Highlight preservation factor (1.0 = smooth highlight roll-off).
        denoise: Enables pre-demosaic FBDD filtering, chroma median passes, and dark pedestal clamping.
        contrast_boost: S-curve contrast enhancement factor (default: 1.0, 1.25 for underexposed recovery).

    Returns:
        The path to the rendered JPEG file.
    """
    if not os.path.exists(dng_path):
        raise FileNotFoundError(f"DNG file not found: {dng_path}")

    os.makedirs(os.path.dirname(os.path.abspath(output_jpg_path)), exist_ok=True)

    with rawpy.imread(dng_path) as raw:
        # Determine white balance settings
        use_cam_wb = (wb_mode == "camera")
        use_auto_wb = (wb_mode == "auto")
        med_passes = 2 if denoise else 0
        fbdd = rawpy.FBDDNoiseReductionMode.Full if denoise else rawpy.FBDDNoiseReductionMode.Off
        noise_t = 300.0 if denoise else 0.0
        ublack = 260 if denoise else -1

        try:
            rgb = raw.postprocess(
                use_camera_wb=use_cam_wb,
                use_auto_wb=use_auto_wb,
                demosaic_algorithm=rawpy.DemosaicAlgorithm.AHD,
                output_color=rawpy.ColorSpace.sRGB,
                output_bps=8,
                no_auto_bright=(exp_shift != 1.0),
                exp_shift=exp_shift,
                exp_preserve_highlights=exp_preserve_highlights,
                median_filter_passes=med_passes,
                fbdd_noise_reduction=fbdd,
                noise_thr=noise_t,
                user_black=ublack,
            )
        except Exception:
            # Fallback to auto white balance if camera WB is unavailable
            rgb = raw.postprocess(
                use_camera_wb=False,
                use_auto_wb=True,
                demosaic_algorithm=rawpy.DemosaicAlgorithm.AHD,
                output_color=rawpy.ColorSpace.sRGB,
                output_bps=8,
                no_auto_bright=(exp_shift != 1.0),
                exp_shift=exp_shift,
                exp_preserve_highlights=exp_preserve_highlights,
                median_filter_passes=med_passes,
                fbdd_noise_reduction=fbdd,
                noise_thr=noise_t,
                user_black=ublack,
            )

    # Save to JPEG via Pillow
    img = Image.fromarray(rgb)
    if contrast_boost != 1.0:
        from PIL import ImageEnhance
        img = ImageEnhance.Contrast(img).enhance(contrast_boost)
    img.save(output_jpg_path, "JPEG", quality=quality, subsampling=subsampling)

    # Copy 100% of metadata, GPS, and timestamp tags from DNG to JPEG
    cmd = [
        "exiftool",
        "-overwrite_original",
        "-q",
        "-TagsFromFile",
        dng_path,
        "-all:all",
        output_jpg_path
    ]
    try:
        subprocess.run(cmd, check=True, timeout=15.0)
    except Exception as e:
        print(f"Warning: Failed to copy metadata from {dng_path} to {output_jpg_path}: {e}", file=sys.stderr)

    return output_jpg_path
