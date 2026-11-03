#!/usr/bin/env python3
"""
byr_pipeline.py - Master pipeline for Tri-Cam .BYR photogrammetry image processing.

End-to-End Workflow:
1. Ingests .BYR files (4KB header + 18.5 MB packed RAW12).
2. Converts raw Bayer pixels into standard Adobe DNG v1.4 RAW files in a designated dng/ folder,
   embedding full EXIF, GPS, camera identity, and timestamp metadata directly into the files.
3. Converts the generated DNG files into high-quality JPEGs in a separate jpg/ folder,
   preserving 100% of geotags and camera tags.
"""

import os
import sys
import argparse
import glob
import time
import json
import csv
from typing import List, Optional
from concurrent.futures import ProcessPoolExecutor, as_completed

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib.byr_reader import BYRFile, BYR_TOTAL_FILE_BYTES
from lib.byr_to_dng import convert_byr_to_dng
from lib.dng_to_jpg import convert_dng_to_jpg
from lib.image_metrics import evaluate_bayer_metrics, ImageQualityMetrics


def _worker_process(args_tuple):
    byr_file, dng_dir, jpg_dir, quality, cfa, wb_mode, auto_ev, manual_ev, denoise, contrast = args_tuple
    return process_single_byr(byr_file, dng_dir, jpg_dir, quality=quality, cfa=cfa, wb_mode=wb_mode,
                              auto_ev=auto_ev, manual_ev=manual_ev, denoise=denoise, contrast=contrast)


def process_single_byr(byr_path: str, dng_dir: str, jpg_dir: str, 
                       quality: int = 95, cfa: Optional[str] = None, wb_mode: str = "auto",
                       auto_ev: bool = False, manual_ev: Optional[float] = None,
                       denoise: bool = False, contrast: float = 1.0) -> dict:
    """
    Processes a single .byr file into both DNG and JPEG outputs with optional auto-gain/EV normalization.
    """
    t0 = time.perf_counter()
    byr = BYRFile(byr_path)
    hdr = byr.header
    pixels = byr.read_pixels()

    # Compute Image Quality Metrics (IQM)
    iqm = evaluate_bayer_metrics(pixels)

    # Determine EV compensation shift and linear gain
    if manual_ev is not None:
        ev_shift = manual_ev
        gain = 2.0 ** manual_ev
    elif auto_ev:
        ev_shift = iqm.recommended_ev_shift
        gain = iqm.recommended_gain
    else:
        ev_shift = None
        gain = 1.0

    base_name = os.path.splitext(os.path.basename(byr_path))[0]
    out_dng_path = os.path.join(dng_dir, f"{base_name}.dng")
    out_jpg_path = os.path.join(jpg_dir, f"{base_name}.jpg")

    # Step 1: BYR -> DNG
    t_dng0 = time.perf_counter()
    convert_byr_to_dng(byr, out_dng_path, compress=False, cfa_override=cfa, baseline_exposure_ev=ev_shift)
    t_dng = (time.perf_counter() - t_dng0) * 1000.0

    # Step 2: DNG -> JPEG
    t_jpg0 = time.perf_counter()
    convert_dng_to_jpg(out_dng_path, out_jpg_path, quality=quality, wb_mode=wb_mode, 
                       exp_shift=gain, exp_preserve_highlights=1.0,
                       denoise=denoise, contrast_boost=contrast)
    t_jpg = (time.perf_counter() - t_jpg0) * 1000.0

    total_ms = (time.perf_counter() - t0) * 1000.0

    return {
        "file": os.path.basename(byr_path),
        "role": hdr.node_role,
        "seq": hdr.seq,
        "lat": hdr.best_latitude,
        "lon": hdr.best_longitude,
        "alt": hdr.best_altitude,
        "dng_path": out_dng_path,
        "jpg_path": out_jpg_path,
        "dng_size_mb": os.path.getsize(out_dng_path) / (1024 * 1024),
        "jpg_size_mb": os.path.getsize(out_jpg_path) / (1024 * 1024),
        "t_dng_ms": t_dng,
        "t_jpg_ms": t_jpg,
        "total_ms": total_ms,
        "iqm": iqm.to_dict(),
        "ev_applied": ev_shift,
        "gain_applied": gain,
    }


def run_pipeline(input_path: str, output_base: str, limit: int = None, 
                 quality: int = 95, cfa: Optional[str] = None, wb_mode: str = "auto",
                 auto_ev: bool = False, manual_ev: Optional[float] = None,
                 export_iqm: bool = True, workers: int = 4,
                 denoise: bool = False, contrast: float = 1.0):
    print("==================================================================")
    print("   GCC X500 Tri-Cam Image Pipeline: .BYR -> DNG -> JPEG           ")
    print("==================================================================")

    # Resolve input files
    if os.path.isfile(input_path):
        byr_files = [input_path]
    elif os.path.isdir(input_path):
        byr_files = sorted(glob.glob(os.path.join(input_path, "**", "*.byr"), recursive=True))
    else:
        print(f"Error: Input path '{input_path}' not found.", file=sys.stderr)
        sys.exit(1)

    if not byr_files:
        print(f"No .byr files found under '{input_path}'.", file=sys.stderr)
        sys.exit(1)

    if limit and limit > 0:
        byr_files = byr_files[:limit]

    dng_dir = os.path.join(output_base, "dng")
    jpg_dir = os.path.join(output_base, "jpg")
    os.makedirs(dng_dir, exist_ok=True)
    os.makedirs(jpg_dir, exist_ok=True)

    ev_mode_str = f"Manual ({manual_ev:+.2f} EV)" if manual_ev is not None else ("Automatic (Midtone Centered)" if auto_ev else "Off (Linear 1.0x)")
    cfa_source_str = f"{cfa} (Manual Override)" if cfa is not None else "Read from .byr container header"
    denoise_str = "Enabled (FBDD + Chroma Median + Dark Clamping)" if denoise else "Disabled (Raw 1:1)"

    print(f"Total .byr files to process: {len(byr_files)}")
    print(f"Target DNG directory       : {dng_dir}")
    print(f"Target JPEG directory      : {jpg_dir}")
    print(f"CFA Pattern Source         : {cfa_source_str}")
    print(f"White Balance Mode         : {wb_mode}")
    print(f"Auto-Gain / EV Adjustment  : {ev_mode_str}")
    print(f"Despeckle / Noise Reduction: {denoise_str}")
    print(f"Contrast Tone Multiplier   : {contrast:.2f}")
    print(f"Parallel Workers           : {workers}\n")

    results = []
    t_start = time.perf_counter()

    if workers > 1 and len(byr_files) > 1:
        tasks = [
            (f, dng_dir, jpg_dir, quality, cfa, wb_mode, auto_ev, manual_ev, denoise, contrast)
            for f in byr_files
        ]
        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_worker_process, t): t[0] for t in tasks}
            for i, future in enumerate(as_completed(futures), 1):
                byr_f = futures[future]
                try:
                    res = future.result()
                    results.append(res)
                    iqm = res["iqm"]
                    ev_info = f" | EV:{res['ev_applied']:+.2f}" if res["ev_applied"] is not None else ""
                    print(f"[{i}/{len(byr_files)}] {res['role']} Seq={res['seq']:09d} ({res['total_ms']:.0f} ms{ev_info}) -> {os.path.basename(res['jpg_path'])}")
                except Exception as e:
                    print(f"[{i}/{len(byr_files)}] [FAIL] {os.path.basename(byr_f)}: {e}", file=sys.stderr)
    else:
        for i, byr_file in enumerate(byr_files, 1):
            print(f"[{i}/{len(byr_files)}] Processing {os.path.basename(byr_file)}...")
            try:
                res = process_single_byr(byr_file, dng_dir, jpg_dir, quality=quality, cfa=cfa, wb_mode=wb_mode,
                                         auto_ev=auto_ev, manual_ev=manual_ev, denoise=denoise, contrast=contrast)
                results.append(res)
                iqm = res["iqm"]
                print(f"      Role={res['role']} Seq={res['seq']:09d} GPS=({res['lat']:.6f}, {res['lon']:.6f}, {res['alt']:.1f}m)")
                print(f"      [IQM] Mean={iqm['mean_dn']:.1f} Median={iqm['median_dn']:.1f} DN | Clipped High={iqm['highlight_clip_pct']:.2f}% Low={iqm['shadow_clip_pct']:.2f}% | Status={iqm['exposure_status']}")
                if res["ev_applied"] is not None:
                    print(f"      [Auto-EV] Applied {res['ev_applied']:+.2f} EV ({res['gain_applied']:.2f}x gain) with highlight preservation")
                print(f"      -> DNG: {res['dng_size_mb']:.2f} MB ({res['t_dng_ms']:.1f} ms) | JPG: {res['jpg_size_mb']:.2f} MB ({res['t_jpg_ms']:.1f} ms)")
            except Exception as e:
                print(f"      [FAIL] Error processing {byr_file}: {e}", file=sys.stderr)

    # Export IQM reports
    if export_iqm and results:
        iqm_json_path = os.path.join(output_base, "image_quality_metrics.json")
        iqm_csv_path = os.path.join(output_base, "image_quality_metrics.csv")

        # JSON
        with open(iqm_json_path, "w") as f:
            json_report = [{
                "file": r["file"],
                "role": r["role"],
                "seq": r["seq"],
                "ev_applied": r["ev_applied"],
                "gain_applied": r["gain_applied"],
                "metrics": r["iqm"]
            } for r in results]
            json.dump(json_report, f, indent=2)

        # CSV
        with open(iqm_csv_path, "w", newline="") as f:
            fieldnames = [
                "file", "role", "seq", "ev_applied", "gain_applied",
                "mean_dn", "median_dn", "min_dn", "max_dn",
                "highlight_clip_pct", "shadow_clip_pct",
                "dynamic_range_stops", "contrast_ratio", "focus_score",
                "exposure_status", "recommended_ev_shift"
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in results:
                m = r["iqm"]
                row = {
                    "file": r["file"], "role": r["role"], "seq": r["seq"],
                    "ev_applied": r["ev_applied"], "gain_applied": r["gain_applied"],
                    "mean_dn": f"{m['mean_dn']:.1f}", "median_dn": f"{m['median_dn']:.1f}",
                    "min_dn": m["min_dn"], "max_dn": m["max_dn"],
                    "highlight_clip_pct": f"{m['highlight_clip_pct']:.2f}",
                    "shadow_clip_pct": f"{m['shadow_clip_pct']:.2f}",
                    "dynamic_range_stops": f"{m['dynamic_range_stops']:.2f}",
                    "contrast_ratio": f"{m['contrast_ratio']:.3f}",
                    "focus_score": f"{m['focus_score']:.1f}",
                    "exposure_status": m["exposure_status"],
                    "recommended_ev_shift": f"{m['recommended_ev_shift']:+.2f}",
                }
                writer.writerow(row)
        print(f"\n[IQM Reports] Saved {iqm_json_path} and {iqm_csv_path}")

    total_duration = time.perf_counter() - t_start
    print("\n==================================================================")
    print(f"   Pipeline Run Complete: {len(results)}/{len(byr_files)} frames processed in {total_duration:.2f} s")
    print(f"   DNG Output: {dng_dir}")
    print(f"   JPG Output: {jpg_dir}")
    print("==================================================================")


def main():
    parser = argparse.ArgumentParser(description="Tri-Cam .BYR -> DNG -> JPEG Processing Pipeline")
    parser.add_argument("--input", "-i", required=True, help="Input .byr file or directory containing .byr files")
    parser.add_argument("--output", "-o", default="output", help="Root directory for outputs (creates dng/ and jpg/)")
    parser.add_argument("--limit", "-l", type=int, default=None, help="Maximum number of files to process")
    parser.add_argument("--quality", "-q", type=int, default=95, help="JPEG quality factor (default: 95)")
    parser.add_argument("--cfa", default=None, help="Optional manual override for Bayer CFA pattern (default: read from .byr header)")
    parser.add_argument("--wb-mode", default="auto", choices=["auto", "camera"], help="White balance mode: 'auto' or 'camera'")
    parser.add_argument("--auto-ev", action="store_true", help="Enable automatic midtone centering and highlight preservation")
    parser.add_argument("--target-ev", type=float, default=None, help="Manual exposure compensation EV shift (e.g. -1.5)")
    parser.add_argument("--workers", "-w", type=int, default=4, help="Number of parallel worker processes (default: 4)")
    parser.add_argument("--no-iqm-report", action="store_true", help="Disable image quality metrics JSON/CSV export")
    parser.add_argument("--denoise", action="store_true", help="Enable FBDD raw wavelet denoising and chroma median filtering")
    parser.add_argument("--contrast", type=float, default=1.0, help="Contrast enhancement multiplier (e.g. 1.25 for underexposed lift)")

    args = parser.parse_args()
    run_pipeline(args.input, args.output, limit=args.limit, quality=args.quality, cfa=args.cfa, wb_mode=args.wb_mode,
                 auto_ev=args.auto_ev, manual_ev=args.target_ev, export_iqm=not args.no_iqm_report, workers=args.workers,
                 denoise=args.denoise, contrast=args.contrast)


if __name__ == "__main__":
    main()
