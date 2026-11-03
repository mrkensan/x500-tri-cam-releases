#!/usr/bin/env python3
"""
de_enroll_triad.py - Multi-SD Card Triad De-enrollment & Offload Engine.

Facilitates offloading imagery from a 3-card photogrammetry triad (Nadir, ObliqueRt, ObliqueFwd)
where cards are mounted one at a time on the workstation:
1. Detects or accepts mounted SD card paths.
2. Identifies the camera node role (Nadir, ObliqueRt, ObliqueFwd) and hardware CID from .byr headers.
3. Copies and verifies .byr imagery into a unified, sortie-indexed project folder structure.
4. Maintains triad_manifest.json tracking cards ingested, file counts, and missing roles.
5. Optionally triggers end-to-end image processing (BYR -> DNG -> JPEG) upon triad completion.
"""

import os
import sys
import shutil
import argparse
import glob
import json
import time
import subprocess
from typing import Dict, List, Optional, Set, Tuple

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib.byr_reader import BYRFile, BYR_TOTAL_FILE_BYTES, BYR_MAGIC

EXPECTED_ROLES = ["Nadir", "ObliqueRt", "ObliqueFwd"]


def find_sdcard_mounts() -> List[str]:
    """
    Finds currently mounted partitions likely to be the RP2W imagery partition.
    Looks for mount points labeled 'imagery' or standard media paths.
    """
    mounts = []
    try:
        res = subprocess.run(["lsblk", "-J", "-o", "NAME,LABEL,MOUNTPOINT,SIZE,FSTYPE"], capture_output=True, text=True)
        if res.returncode == 0:
            data = json.loads(res.stdout)
            def scan_devs(dev_list):
                for dev in dev_list:
                    label = (dev.get("label") or "").lower()
                    mp = dev.get("mountpoint")
                    if mp and (label == "imagery" or "imagery" in mp.lower()):
                        mounts.append(mp)
                    if "children" in dev:
                        scan_devs(dev["children"])
            scan_devs(data.get("blockdevices", []))
    except Exception:
        pass

    # Also check /mnt/sd_imagery and /media/$USER/imagery
    for candidate in ["/mnt/sd_imagery", "/media/imagery"]:
        if os.path.ismount(candidate) or (os.path.isdir(candidate) and glob.glob(os.path.join(candidate, "**", "*.byr"), recursive=True)):
            if candidate not in mounts:
                mounts.append(candidate)

    return mounts


def scan_source_card(source_dir: str) -> Dict[str, Dict]:
    """
    Scans a source directory/card for .byr files and groups them by task_uuid.
    Returns: { task_uuid: { 'role': str, 'files': [paths], 'hdr_sample': BYRHeader, 'seqs': [int] } }
    """
    byr_paths = sorted(glob.glob(os.path.join(source_dir, "**", "*.byr"), recursive=True))
    if not byr_paths:
        return {}

    sorties = {}
    for p in byr_paths:
        try:
            # Read header only for fast indexing
            with open(p, "rb") as f:
                magic = f.read(4)
            if magic != BYR_MAGIC:
                continue

            byr = BYRFile(p)
            hdr = byr.header
            uuid_hex = hdr.task_uuid_hex or "unknown_sortie"

            if uuid_hex not in sorties:
                sorties[uuid_hex] = {
                    "role": hdr.node_role,
                    "node_id": hdr.node_id,
                    "bcm_cpu_serial": f"0x{hdr.bcm_cpu_serial:016X}",
                    "sd_card_cid": hdr.sd_card_cid.hex() if hdr.sd_card_cid else "",
                    "files": [],
                    "seqs": [],
                    "hdr_sample": hdr,
                }
            sorties[uuid_hex]["files"].append(p)
            sorties[uuid_hex]["seqs"].append(hdr.seq)
        except Exception as e:
            print(f"Warning: Failed to parse header of {p}: {e}", file=sys.stderr)

    return sorties


class TriadManifest:
    def __init__(self, sortie_dir: str, task_uuid: str):
        self.sortie_dir = sortie_dir
        self.task_uuid = task_uuid
        self.manifest_path = os.path.join(sortie_dir, "triad_manifest.json")
        self.data = self._load()

    def _load(self) -> dict:
        if os.path.exists(self.manifest_path):
            try:
                with open(self.manifest_path, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "task_uuid": self.task_uuid,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "last_updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "triad_complete": False,
            "cards_ingested": {},
            "total_byr_files": 0,
            "complete_triplets": 0,
            "missing_roles": list(EXPECTED_ROLES),
        }

    def record_card_ingest(self, role: str, node_id: int, cpu_serial: str, sd_cid: str, 
                           file_count: int, seq_min: int, seq_max: int, files_copied: int,
                           logs: Optional[Dict[str, str]] = None):
        self.data["last_updated"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.data["cards_ingested"][role] = {
            "node_id": node_id,
            "bcm_cpu_serial": cpu_serial,
            "sd_card_cid": sd_cid,
            "file_count": file_count,
            "seq_range": [seq_min, seq_max],
            "ingested_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "newly_copied": files_copied,
            "logs": logs or {},
        }

        # Update missing roles
        ingested_roles = list(self.data["cards_ingested"].keys())
        self.data["missing_roles"] = [r for r in EXPECTED_ROLES if r not in ingested_roles]
        self.data["triad_complete"] = (len(self.data["missing_roles"]) == 0)

        # Count total files
        total_files = len(glob.glob(os.path.join(self.sortie_dir, "byr", "*.byr")))
        self.data["total_byr_files"] = total_files

        # Save manifest
        with open(self.manifest_path, "w") as f:
            json.dump(self.data, f, indent=2)

    def print_status(self):
        print("\n------------------------------------------------------------------")
        print(f"   Sortie UUID: {self.task_uuid}")
        print("------------------------------------------------------------------")
        ingested = self.data["cards_ingested"]
        for role in EXPECTED_ROLES:
            if role in ingested:
                info = ingested[role]
                seq_r = f"Seq {info['seq_range'][0]:09d}..{info['seq_range'][1]:09d}"
                log_names = list(info.get("logs", {}).values())
                log_str = f" | Logs: {', '.join(log_names)}" if log_names else ""
                print(f"  [X] {role:<12} : INGESTED ({info['file_count']} files, {seq_r}, Node {info['node_id']}{log_str})")
            else:
                print(f"  [ ] {role:<12} : PENDING / NOT YET MOUNTED")

        status_str = "COMPLETE (3/3 Cards)" if self.data["triad_complete"] else f"PARTIAL ({len(ingested)}/3 Cards)"
        print(f"\n  Triad Status : {status_str}")
        print(f"  Total Files  : {self.data['total_byr_files']} .byr files")
        if self.data["missing_roles"]:
            print(f"  Waiting for  : {', '.join(self.data['missing_roles'])}")
        print("------------------------------------------------------------------\n")


def find_and_copy_card_logs(source_dir: str, sortie_dir: str, role: str) -> Dict[str, str]:
    """
    Finds session.log, .card_benchmark, and other diagnostic logs on the SD card
    and copies them to <sortie_dir>/logs/ tagged with the camera role.
    """
    logs_dest_dir = os.path.join(sortie_dir, "logs")
    os.makedirs(logs_dest_dir, exist_ok=True)

    copied_logs = {}

    # Candidate root directories (source_dir and its parent mount point)
    candidate_dirs = [source_dir]
    parent = os.path.dirname(os.path.abspath(source_dir))
    if parent and parent != "/" and parent not in candidate_dirs:
        candidate_dirs.append(parent)

    discovered_files = []
    for cdir in candidate_dirs:
        for fname in ["session.log", ".card_benchmark", "card_benchmark.txt"]:
            fpath = os.path.join(cdir, fname)
            if os.path.isfile(fpath) and fpath not in discovered_files:
                discovered_files.append(fpath)

    # Also find any other *.log files under source_dir
    for fpath in glob.glob(os.path.join(source_dir, "**", "*.log"), recursive=True):
        if fpath not in discovered_files:
            discovered_files.append(fpath)

    for src_log in discovered_files:
        base = os.path.basename(src_log)
        if base == "session.log":
            dst_name = f"session_{role}.log"
        elif base.startswith(".card_benchmark") or "benchmark" in base:
            dst_name = f"card_benchmark_{role}.txt"
        else:
            name_part, ext = os.path.splitext(base)
            dst_name = f"{name_part}_{role}{ext}"

        dst_path = os.path.join(logs_dest_dir, dst_name)
        try:
            shutil.copyfile(src_log, dst_path)
            copied_logs[base] = os.path.relpath(dst_path, sortie_dir)
            size_kb = os.path.getsize(dst_path) / 1024.0
            print(f"  [LOG] Offloaded {base} ({size_kb:.1f} KB) -> logs/{dst_name}")
        except Exception as e:
            print(f"  [WARN] Failed to copy log {src_log}: {e}", file=sys.stderr)

    return copied_logs


def de_enroll_card(source_dir: str, dest_root: str, auto_unmount: bool = False) -> Dict[str, TriadManifest]:
    """
    De-enrolls all photos from a currently mounted SD card into destination folders.
    """
    print(f"Scanning card at: {source_dir}...")
    sorties = scan_source_card(source_dir)

    if not sorties:
        print(f"No valid .byr image containers found on {source_dir}.")
        return {}

    manifests = {}
    for uuid_hex, info in sorties.items():
        role = info["role"]
        node_id = info["node_id"]
        files = info["files"]
        seqs = info["seqs"]
        cpu_serial = info["bcm_cpu_serial"]
        sd_cid = info["sd_card_cid"]

        sortie_dir = os.path.join(dest_root, uuid_hex)
        byr_dest_dir = os.path.join(sortie_dir, "byr")
        os.makedirs(byr_dest_dir, exist_ok=True)

        manifest = TriadManifest(sortie_dir, uuid_hex)
        manifests[uuid_hex] = manifest

        print(f"\nFound Sortie {uuid_hex}:")
        print(f"  Camera Role : {role} (Node {node_id})")
        print(f"  Files Count : {len(files)} .byr frames")
        print(f"  Sequence    : {min(seqs):09d} .. {max(seqs):09d}")
        print(f"  Destination : {byr_dest_dir}")

        copied_count = 0
        skipped_count = 0
        t0 = time.perf_counter()
        total_bytes = 0

        for i, src_f in enumerate(files, 1):
            fname = os.path.basename(src_f)
            dst_f = os.path.join(byr_dest_dir, fname)

            # Skip if file already exists with matching size
            if os.path.exists(dst_f) and os.path.getsize(dst_f) == os.path.getsize(src_f):
                skipped_count += 1
                continue

            shutil.copyfile(src_f, dst_f)
            copied_count += 1
            total_bytes += os.path.getsize(dst_f)

            if i % 10 == 0 or i == len(files):
                print(f"  Offloading [{i}/{len(files)}] {fname}...")

        duration = time.perf_counter() - t0
        mb_copied = total_bytes / (1024 * 1024)
        speed = (mb_copied / duration) if duration > 0.001 else 0.0

        print(f"  Copied {copied_count} files ({mb_copied:.1f} MB in {duration:.1f}s, {speed:.1f} MB/s), Skipped {skipped_count} existing.")

        # Capture session.log, .card_benchmark, and other diagnostic logs from this card
        copied_logs = find_and_copy_card_logs(source_dir, sortie_dir, role)

        manifest.record_card_ingest(
            role=role,
            node_id=node_id,
            cpu_serial=cpu_serial,
            sd_cid=sd_cid,
            file_count=len(files),
            seq_min=min(seqs),
            seq_max=max(seqs),
            files_copied=copied_count,
            logs=copied_logs,
        )
        manifest.print_status()

    # Sync OS disk buffers
    try:
        subprocess.run(["sync"])
    except Exception:
        pass

    if auto_unmount:
        print(f"Safely unmounting {source_dir}...")
        try:
            subprocess.run(["udisksctl", "unmount", "-p", source_dir], capture_output=True)
            print("  Card successfully unmounted. Safe to remove.")
        except Exception:
            try:
                subprocess.run(["umount", source_dir], capture_output=True)
                print("  Card successfully unmounted. Safe to remove.")
            except Exception as e:
                print(f"  Notice: Could not unmount {source_dir}: {e}. Please unmount manually.")

    return manifests


def interactive_wizard(dest_root: str, auto_unmount: bool = True):
    """
    Interactive guided wizard to de-enroll all 3 cards of a triad sequentially.
    """
    print("==================================================================")
    print("   Tri-Cam SD Card Triad De-Enrollment Wizard                     ")
    print("==================================================================")
    print(f"Target Destination Root: {os.path.abspath(dest_root)}")
    print("You will insert and mount the 3 SD cards (Nadir, ObliqueRt, ObliqueFwd) one at a time.\n")

    card_step = 1
    active_manifests = {}

    while True:
        print(f"\n>>> [Card {card_step}] Please insert and mount SD card {card_step} of 3.")
        input("Press [Enter] once the card is mounted (or type 'q' to finish): ")

        # Look for mounted cards
        mounts = find_sdcard_mounts()
        if not mounts:
            user_path = input("No automount detected. Enter path to mounted card (e.g. /media/user/imagery): ").strip()
            if user_path and os.path.isdir(user_path):
                mounts = [user_path]
            elif user_path.lower() == 'q':
                break
            else:
                print("Invalid path or no card found. Retrying...")
                continue

        source_path = mounts[0]
        print(f"Using card at: {source_path}")

        manifests = de_enroll_card(source_path, dest_root, auto_unmount=auto_unmount)
        active_manifests.update(manifests)

        # Check if all sorties have complete triads
        all_complete = True
        for uuid_hex, m in active_manifests.items():
            if not m.data["triad_complete"]:
                all_complete = False

        if all_complete and active_manifests:
            print("\n*** SUCCESS: ALL 3 CARDS IN TRIAD SUCCESSFULLY DE-ENROLLED! ***")
            for m in active_manifests.values():
                m.print_status()

            run_now = input("Would you like to run the image pipeline (BYR -> DNG -> JPG) now? [Y/n]: ").strip().lower()
            if run_now != 'n':
                for uuid_hex, m in active_manifests.items():
                    byr_dir = os.path.join(m.sortie_dir, "byr")
                    print(f"\nRunning pipeline on {byr_dir}...")
                    cmd = [sys.executable, "byr_pipeline.py", "--input", byr_dir, "--output", m.sortie_dir]
                    subprocess.run(cmd)
            break

        cont = input("\nReady for the next card? [Y/q]: ").strip().lower()
        if cont == 'q':
            break
        card_step += 1


def main():
    parser = argparse.ArgumentParser(description="Tri-Cam SD Card Triad De-Enrollment Tool")
    parser.add_argument("--source", "-s", help="Path to mounted SD card directory (e.g. /mnt/sd_imagery)")
    parser.add_argument("--dest", "-d", default="triad_datasets", help="Destination root directory for sorties")
    parser.add_argument("--wizard", "-w", action="store_true", help="Launch interactive 3-card insertion wizard")
    parser.add_argument("--unmount", "-u", action="store_true", help="Safely unmount SD card after copying")

    args = parser.parse_args()

    if args.wizard or not args.source:
        # If no source provided, default to wizard mode
        interactive_wizard(args.dest, auto_unmount=args.unmount)
    else:
        de_enroll_card(args.source, args.dest, auto_unmount=args.unmount)


if __name__ == "__main__":
    main()
