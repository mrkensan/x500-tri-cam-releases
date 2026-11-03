#!/usr/bin/env python3
"""
tricam_ingest.py - Multi-Camera Photogrammetry Dataset Ingestion Engine.

Ingests raw .BYR imagery across 3 camera nodes (Nadir, ObliqueRt, ObliqueFwd),
groups frames into synchronized capture triplets by master sequence index (seq),
validates synchronization integrity, and renders complete DNG and JPEG image sets.
"""

import os
import sys
import glob
import argparse
import json
import csv
import time
from collections import defaultdict
from typing import Dict, List, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib.byr_reader import BYRFile, BYRHeader
from lib.byr_to_dng import convert_byr_to_dng
from lib.dng_to_jpg import convert_dng_to_jpg

CAMERA_ROLES = ["Nadir", "ObliqueRt", "ObliqueFwd"]


class TriCamDataset:
    def __init__(self):
        # Keyed by seq number -> {role: BYRFile}
        self.triplets: Dict[int, Dict[str, BYRFile]] = defaultdict(dict)
        self.orphans: List[BYRFile] = []

    def scan_path(self, path: str):
        """
        Recursively scans a directory or list of files for .byr containers.
        """
        if os.path.isfile(path) and path.endswith(".byr"):
            files = [path]
        elif os.path.isdir(path):
            files = sorted(glob.glob(os.path.join(path, "**", "*.byr"), recursive=True))
        else:
            return

        for f in files:
            try:
                byr = BYRFile(f)
                hdr = byr.header
                role = hdr.node_role
                seq = hdr.seq
                self.triplets[seq][role] = byr
            except Exception as e:
                print(f"Warning: Failed to parse {f}: {e}", file=sys.stderr)

    def analyze(self) -> dict:
        total_triplets = 0
        partial_sets = 0
        role_counts = defaultdict(int)

        for seq, group in self.triplets.items():
            for role in group.keys():
                role_counts[role] += 1
            if len(group) == 3:
                total_triplets += 1
            else:
                partial_sets += 1

        return {
            "total_sequences": len(self.triplets),
            "complete_triplets": total_triplets,
            "partial_sequences": partial_sets,
            "counts_by_role": dict(role_counts),
        }

    def export_manifest(self, output_dir: str):
        """
        Generates manifest.json and triplets.csv describing the ingested photo-set.
        """
        os.makedirs(output_dir, exist_ok=True)
        manifest_path = os.path.join(output_dir, "manifest.json")
        csv_path = os.path.join(output_dir, "triplets.csv")

        triplet_rows = []
        for seq in sorted(self.triplets.keys()):
            group = self.triplets[seq]
            row = {
                "seq": f"{seq:09d}",
                "complete": (len(group) == 3),
                "nadir_file": os.path.basename(group["Nadir"].file_path) if "Nadir" in group else "",
                "oblique_rt_file": os.path.basename(group["ObliqueRt"].file_path) if "ObliqueRt" in group else "",
                "oblique_fwd_file": os.path.basename(group["ObliqueFwd"].file_path) if "ObliqueFwd" in group else "",
            }
            # Add navigation info from any available camera in the group
            any_byr = next(iter(group.values()))
            row["lat"] = f"{any_byr.header.best_latitude:.8f}"
            row["lon"] = f"{any_byr.header.best_longitude:.8f}"
            row["alt"] = f"{any_byr.header.best_altitude:.2f}"
            row["gps_tow_ms"] = any_byr.header.gps_tow_ms
            row["task_uuid"] = any_byr.header.task_uuid_hex
            triplet_rows.append(row)

        with open(csv_path, "w", newline="") as f:
            fieldnames = ["seq", "complete", "nadir_file", "oblique_rt_file", "oblique_fwd_file", "lat", "lon", "alt", "gps_tow_ms", "task_uuid"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(triplet_rows)

        summary = self.analyze()
        summary["manifest_csv"] = csv_path
        with open(manifest_path, "w") as f:
            json.dump(summary, f, indent=2)

        print(f"Dataset manifest written: {manifest_path}")
        print(f"Triplet cross-reference written: {csv_path}")

    def render(self, output_dir: str, render_dng: bool = True, render_jpg: bool = True, limit: int = None, quality: int = 95):
        """
        Converts ingested BYR files into organized DNG and JPEG directories.
        """
        dng_dir = os.path.join(output_dir, "dng")
        jpg_dir = os.path.join(output_dir, "jpg")

        if render_dng:
            os.makedirs(dng_dir, exist_ok=True)
        if render_jpg:
            os.makedirs(jpg_dir, exist_ok=True)

        seqs = sorted(self.triplets.keys())
        if limit and limit > 0:
            seqs = seqs[:limit]

        total_frames = sum(len(self.triplets[s]) for s in seqs)
        processed = 0

        print(f"Rendering {len(seqs)} trigger epochs ({total_frames} total frames)...")

        for seq in seqs:
            group = self.triplets[seq]
            for role in sorted(group.keys()):
                byr = group[role]
                base_name = os.path.splitext(os.path.basename(byr.file_path))[0]
                out_dng = os.path.join(dng_dir, f"{base_name}.dng")
                out_jpg = os.path.join(jpg_dir, f"{base_name}.jpg")

                processed += 1
                print(f"  [{processed}/{total_frames}] {role} Seq={seq:09d}...")

                if render_dng or render_jpg:
                    convert_byr_to_dng(byr, out_dng, compress=False)
                if render_jpg:
                    convert_dng_to_jpg(out_dng, out_jpg, quality=quality)

        self.export_manifest(output_dir)


def main():
    parser = argparse.ArgumentParser(description="Tri-Cam 3-Camera Dataset Ingestion & Harmonization")
    parser.add_argument("--inputs", "-i", nargs="+", required=True, help="Input directories or SD card mount paths")
    parser.add_argument("--output", "-o", default="dataset_output", help="Unified project output directory")
    parser.add_argument("--limit", "-l", type=int, default=None, help="Maximum number of sequences to process")
    parser.add_argument("--no-dng", action="store_true", help="Skip DNG rendering")
    parser.add_argument("--no-jpg", action="store_true", help="Skip JPEG rendering")
    parser.add_argument("--quality", "-q", type=int, default=95, help="JPEG quality (default: 95)")

    args = parser.parse_args()

    print("==================================================================")
    print("   Tri-Cam Multi-Camera Photogrammetry Dataset Ingest            ")
    print("==================================================================")

    dataset = TriCamDataset()
    for inp in args.inputs:
        print(f"Scanning input source: {inp}...")
        dataset.scan_path(inp)

    stats = dataset.analyze()
    print(f"\nIngestion Analysis:")
    print(f"  Unique Trigger Epochs : {stats['total_sequences']}")
    print(f"  Complete (3x) Triplets: {stats['complete_triplets']}")
    print(f"  Partial Sequences     : {stats['partial_sequences']}")
    for role, count in stats["counts_by_role"].items():
        print(f"  -> {role:<12}: {count} frames")

    dataset.render(
        args.output,
        render_dng=not args.no_dng,
        render_jpg=not args.no_jpg,
        limit=args.limit,
        quality=args.quality,
    )


if __name__ == "__main__":
    main()
