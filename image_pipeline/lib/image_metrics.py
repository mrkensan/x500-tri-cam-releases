"""
image_metrics.py - Image Quality Metrics (IQM) and Radiometric Analysis for Tri-Cam Bayer Imagery.

Evaluates raw sensor dynamic range, clipping percentages, midtone centering,
and computes optimal auto-exposure compensation (EV shifts) for dev visualization.
"""

import math
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional
import numpy as np


@dataclass
class ImageQualityMetrics:
    # Basic statistics
    min_dn: int
    max_dn: int
    mean_dn: float
    median_dn: float

    # Percentiles
    p01_dn: float
    p05_dn: float
    p25_dn: float
    p75_dn: float
    p95_dn: float
    p99_dn: float

    # Radiometric Clipping
    highlight_clip_pct: float  # Pixels >= 4090 DN
    shadow_clip_pct: float     # Pixels <= 258 DN (black pedestal)

    # Dynamic range & contrast
    dynamic_range_stops: float # log2(P99 / P01)
    contrast_ratio: float      # (P95 - P05) / mean

    # Diagnostic Focus & Sharpness
    focus_score: float         # High-frequency gradient variance

    # Exposure Assessment
    exposure_status: str       # 'OVEREXPOSED', 'UNDEREXPOSED', or 'BALANCED'
    recommended_ev_shift: float # In stops (e.g. -1.5 EV or +0.8 EV)
    recommended_gain: float    # Linear multiplier (2^EV)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def evaluate_bayer_metrics(pixels: np.ndarray, 
                           black_level: int = 256, 
                           white_level: int = 4095,
                           target_midtone_dn: int = 947) -> ImageQualityMetrics:
    """
    Computes comprehensive image quality metrics on raw 12-bit Bayer pixels.

    Args:
        pixels: 2D uint16 array of raw sensor values [0..4095].
        black_level: Optical black pedestal (default: 256).
        white_level: ADC saturation ceiling (default: 4095).
        target_midtone_dn: Target 18% gray linear DN (default: 256 + 0.18*(4095-256) = 947).

    Returns:
        ImageQualityMetrics dataclass.
    """
    total_pixels = pixels.size
    min_dn = int(pixels.min())
    max_dn = int(pixels.max())
    mean_dn = float(pixels.mean())
    median_dn = float(np.median(pixels))

    # Clipping counts
    hi_clip_count = int(np.count_nonzero(pixels >= (white_level - 5)))
    lo_clip_count = int(np.count_nonzero(pixels <= (black_level + 2)))
    hi_clip_pct = (hi_clip_count / total_pixels) * 100.0
    lo_clip_pct = (lo_clip_count / total_pixels) * 100.0

    # Percentiles
    p01, p05, p25, p75, p95, p99 = [
        float(x) for x in np.percentile(pixels, [1, 5, 25, 75, 95, 99])
    ]

    # Dynamic Range (stops above pedestal)
    p01_eff = max(1.0, p01 - black_level)
    p99_eff = max(1.0, p99 - black_level)
    dr_stops = math.log2(p99_eff / p01_eff) if p99_eff > p01_eff else 0.0

    # Contrast
    contrast = (p95 - p05) / mean_dn if mean_dn > 0 else 0.0

    # Focus Score: High-frequency Laplacian variance on green channels
    # Green pixels are at [0::2, 1::2] and [1::2, 0::2]
    green_sub = pixels[0::2, 1::2].astype(np.float32)
    # 2D Laplacian kernel convolution via slice difference
    diff_h = np.diff(green_sub, axis=1)
    diff_v = np.diff(green_sub, axis=0)
    focus_score = float((np.var(diff_h) + np.var(diff_v)) / 2.0)

    # Exposure Status & EV Shift Calculation
    target_eff = float(target_midtone_dn - black_level) # ~691 DN
    median_eff = max(1.0, median_dn - black_level)

    # Ideal gain ratio to place median at 18% gray
    gain_ratio = target_eff / median_eff

    # Highlight protection: prevent P99 from blowing past 3900 DN
    if p99 > black_level:
        max_allowed_gain = (3900.0 - black_level) / (p99 - black_level)
        if gain_ratio > max_allowed_gain:
            gain_ratio = max_allowed_gain

    # Clamp EV adjustment to reasonable limits [-3.5 EV .. +3.5 EV]
    gain_ratio = max(0.088, min(11.31, gain_ratio))
    ev_shift = math.log2(gain_ratio)

    if hi_clip_pct >= 2.0 or ev_shift <= -1.0:
        status = "OVEREXPOSED"
    elif lo_clip_pct >= 20.0 or ev_shift >= 1.5:
        status = "UNDEREXPOSED"
    else:
        status = "BALANCED"

    return ImageQualityMetrics(
        min_dn=min_dn,
        max_dn=max_dn,
        mean_dn=mean_dn,
        median_dn=median_dn,
        p01_dn=p01,
        p05_dn=p05,
        p25_dn=p25,
        p75_dn=p75,
        p95_dn=p95,
        p99_dn=p99,
        highlight_clip_pct=hi_clip_pct,
        shadow_clip_pct=lo_clip_pct,
        dynamic_range_stops=dr_stops,
        contrast_ratio=contrast,
        focus_score=focus_score,
        exposure_status=status,
        recommended_ev_shift=ev_shift,
        recommended_gain=gain_ratio,
    )
