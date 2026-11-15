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
import getpass
import platform
import re
import subprocess
from typing import Dict, List, Optional, Set, Tuple

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib.byr_reader import BYRFile, BYR_TOTAL_FILE_BYTES, BYR_MAGIC

EXPECTED_ROLES = ["Nadir", "ObliqueRt", "ObliqueFwd"]
RECEIPTS_DIR = os.path.expanduser("~/.tri-cam-receipts")


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


_SORTIE_IN_NAME = re.compile(r"^[0-9a-fA-F]{32}_[A-Za-z]+_(\d{6}_\d{4})_\d{4,}\.byr$")   # UUID_ROLE_SORTIE_SEQ.byr
_SORTIE_FOLDER = re.compile(r"^(\d{6}_\d{4})_[0-9a-fA-F]{8}$")                         # SORTIE_UUID8/


def sortie_of(path: str) -> Optional[str]:
    """The sortie ID (YYMMDD_HHMM, UTC at arming) of a node's image file, from its name or its sortie folder."""
    m = _SORTIE_IN_NAME.match(os.path.basename(path))
    if m:
        return m.group(1)
    m = _SORTIE_FOLDER.match(os.path.basename(os.path.dirname(os.path.abspath(path))))
    return m.group(1) if m else None


def dataset_folder(task_uuid: str, sortie: Optional[str]) -> str:
    """One dataset per mission and sortie, named as on the cards: SORTIE_UUID8 (the full UUID is in the manifest)."""
    return f"{sortie}_{task_uuid[:8]}" if sortie else task_uuid


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
            sortie = sortie_of(p)
            key = f"{sortie}_{uuid_hex}" if sortie else uuid_hex     # a mission flown twice is two datasets

            if key not in sorties:
                sorties[key] = {
                    "task_uuid": uuid_hex,
                    "sortie_id": sortie,
                    "role": hdr.node_role,
                    "node_id": hdr.node_id,
                    "bcm_cpu_serial": f"0x{hdr.bcm_cpu_serial:016X}",
                    "sd_card_cid": hdr.sd_card_cid.hex() if hdr.sd_card_cid else "",
                    "files": [],
                    "seqs": [],
                    "hdr_sample": hdr,
                    "source_sortie_dir": os.path.dirname(os.path.abspath(p)),
                }
            sorties[key]["files"].append(p)
            sorties[key]["seqs"].append(hdr.seq)
        except Exception as e:
            print(f"Warning: Failed to parse header of {p}: {e}", file=sys.stderr)

    return sorties


def compute_seq_segments(seqs: List[int]) -> Tuple[List[List[int]], List[List[int]], str]:
    """
    Computes contiguous sequence ranges and identifies any dropped sequence spans.
    Returns: (seq_ranges, dropped_seq_spans, seq_continuity)
    """
    if not seqs:
        return [], [], "EMPTY"

    unique_seqs = sorted(set(seqs))
    seq_ranges = []
    dropped_seq_spans = []

    start = unique_seqs[0]
    prev = start

    for s in unique_seqs[1:]:
        if s == prev + 1:
            prev = s
        else:
            seq_ranges.append([start, prev])
            dropped_seq_spans.append([prev + 1, s - 1])
            start = s
            prev = s
    seq_ranges.append([start, prev])

    continuity = "CONTIGUOUS" if not dropped_seq_spans else "GAPS_DETECTED"
    return seq_ranges, dropped_seq_spans, continuity


def emit_offload_receipt(
    source_sortie_dir: str,
    dest_sortie_dir: str,
    task_uuid: str,
    role: str,
    node_id: int,
    bcm_cpu_serial: str,
    sd_card_cid: str,
    file_count: int,
    seq_ranges: List[List[int]],
    dropped_seq_spans: List[List[int]],
    seq_continuity: str,
    source_mount: str,
) -> Tuple[Optional[str], Optional[str], dict]:
    """
    Emits an offload receipt to the source SD card directory and to ~/.tri-cam-receipts/.
    Returns (card_receipt_path, host_receipt_path, receipt_dict).
    """
    ts_str = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
    ts_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    user = getpass.getuser() or os.environ.get("USER", "unknown")
    host = platform.node() or "unknown"

    receipt_data = {
        "schema_version": 1,
        "task_uuid": task_uuid,
        "role": role,
        "node_id": node_id,
        "bcm_cpu_serial": bcm_cpu_serial,
        "sd_card_cid": sd_card_cid,
        "file_count": file_count,
        "seq_ranges": seq_ranges,
        "dropped_seq_spans": dropped_seq_spans,
        "seq_continuity": seq_continuity,
        "offloaded_at_utc": ts_iso,
        "offloader_user": user,
        "offloader_host": host,
        "destination_path": os.path.abspath(dest_sortie_dir),
        "source_mount": os.path.abspath(source_mount),
        "status": "VERIFIED_COMPLETE",
    }

    card_receipt_path = None
    host_receipt_path = None

    # 1. Write host ledger receipt
    try:
        os.makedirs(RECEIPTS_DIR, exist_ok=True)
        h_name = f"{task_uuid}_{role}_{ts_str}.json"
        host_receipt_path = os.path.join(RECEIPTS_DIR, h_name)
        with open(host_receipt_path, "w") as f:
            json.dump(receipt_data, f, indent=2)
    except Exception as e:
        print(f"  [WARN] Failed to write host ledger receipt to {RECEIPTS_DIR}: {e}", file=sys.stderr)

    # 2. Write card-side receipt
    if os.path.isdir(source_sortie_dir):
        c_name = f".offload_receipt_{ts_str}.json"
        card_receipt_path = os.path.join(source_sortie_dir, c_name)
        try:
            with open(card_receipt_path, "w") as f:
                json.dump(receipt_data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            try:
                subprocess.run(["sync"], check=False)
            except Exception:
                pass
            print(f"  [RECEIPT] Card receipt written: {c_name} (User: {user}@{host})")
        except OSError as e:
            card_receipt_path = None
            print(f"\n  [!] WARNING: SD CARD IS MOUNTED READ-ONLY! ({e})", file=sys.stderr)
            print(f"      Imagery was copied to workstation, but receipt could NOT be written to SD card.", file=sys.stderr)
            print(f"      Host receipt preserved at: {host_receipt_path}", file=sys.stderr)
            print(f"      NOTICE: sd-prep.sh will block wiping this card until an offload receipt exists on media!\n", file=sys.stderr)

    return card_receipt_path, host_receipt_path, receipt_data


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

    def is_duplicate_card(self, role: str, sd_cid: str) -> Optional[Tuple[str, dict]]:
        """
        Checks if role or sd_cid has already been ingested into this sortie manifest.
        Returns (existing_role, existing_info) if duplicate, else None.
        """
        ingested = self.data.get("cards_ingested", {})
        if role in ingested:
            return role, ingested[role]
        if sd_cid:
            for ex_role, ex_info in ingested.items():
                if ex_info.get("sd_card_cid") and ex_info.get("sd_card_cid") == sd_cid:
                    return ex_role, ex_info
        return None

    def record_card_ingest(self, role: str, node_id: int, cpu_serial: str, sd_cid: str, 
                           file_count: int, seq_min: int, seq_max: int, files_copied: int,
                           seq_ranges: Optional[List[List[int]]] = None,
                           dropped_seq_spans: Optional[List[List[int]]] = None,
                           seq_continuity: str = "CONTIGUOUS",
                           receipts: Optional[Dict[str, str]] = None,
                           offloader_user: Optional[str] = None,
                           logs: Optional[Dict[str, str]] = None):
        self.data["last_updated"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.data["cards_ingested"][role] = {
            "node_id": node_id,
            "bcm_cpu_serial": cpu_serial,
            "sd_card_cid": sd_cid,
            "file_count": file_count,
            "seq_range": [seq_min, seq_max],
            "seq_ranges": seq_ranges or [[seq_min, seq_max]],
            "dropped_seq_spans": dropped_seq_spans or [],
            "seq_continuity": seq_continuity,
            "ingested_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "offloader_user": offloader_user or getpass.getuser() or "unknown",
            "newly_copied": files_copied,
            "receipts": receipts or {},
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


class DeEnrollResult(dict):
    """
    Subclass of dict to preserve backward compatibility with result[task_uuid]
    while exposing duplicate_detected and duplicates list to callers.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.duplicate_detected = False
        self.duplicates = []


def find_and_copy_card_logs(source_dir: str, sortie_dir: str, role: str, sortie_prefix: Optional[str] = None) -> Dict[str, str]:
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

    # Also find any other *.log files under source_dir (with a sortie: only that sortie's, SORTIE_UUID8_ROLE.log)
    for fpath in glob.glob(os.path.join(source_dir, "**", "*.log"), recursive=True):
        if sortie_prefix and os.path.basename(fpath) != "session.log" and not os.path.basename(fpath).startswith(sortie_prefix):
            continue
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
            dst_name = base if sortie_prefix and base.startswith(sortie_prefix) else f"{name_part}_{role}{ext}"

        dst_path = os.path.join(logs_dest_dir, dst_name)
        try:
            shutil.copyfile(src_log, dst_path)
            copied_logs[base] = os.path.relpath(dst_path, sortie_dir)
            size_kb = os.path.getsize(dst_path) / 1024.0
            print(f"  [LOG] Offloaded {base} ({size_kb:.1f} KB) -> logs/{dst_name}")
        except Exception as e:
            print(f"  [WARN] Failed to copy log {src_log}: {e}", file=sys.stderr)

    return copied_logs


def de_enroll_card(source_dir: str, dest_root: str, auto_unmount: bool = False, force_duplicate: bool = False) -> DeEnrollResult:
    """
    De-enrolls all photos from a currently mounted SD card into destination folders.
    Enforces atomic copy verification, duplicate card detection, and dual-receipt emission.
    """
    print(f"Scanning card at: {source_dir}...")
    sorties = scan_source_card(source_dir)

    manifests = DeEnrollResult()
    if not sorties:
        print(f"No valid .byr image containers found on {source_dir}.")
        return manifests

    for key, info in sorties.items():
        uuid_hex = info.get("task_uuid", key)
        sortie = info.get("sortie_id")
        role = info["role"]
        node_id = info["node_id"]
        files = info["files"]
        seqs = info["seqs"]
        cpu_serial = info["bcm_cpu_serial"]
        sd_cid = info["sd_card_cid"]
        source_sortie_dir = info.get("source_sortie_dir") or source_dir

        sortie_dir = os.path.join(dest_root, dataset_folder(uuid_hex, sortie))
        byr_dest_dir = os.path.join(sortie_dir, "byr")
        os.makedirs(byr_dest_dir, exist_ok=True)

        manifest = TriadManifest(sortie_dir, uuid_hex)
        if manifest.data.get("task_uuid", uuid_hex) != uuid_hex:
            print(f"  [ERROR] {sortie_dir} already holds mission {manifest.data.get('task_uuid')}, not {uuid_hex}: "
                  "two missions share a sortie folder name. Not merged; offload this card to another destination.",
                  file=sys.stderr)
            continue
        if sortie:
            manifest.data["sortie_id"] = sortie
        manifests[key] = manifest

        # Check for Duplicate Card Re-Insertion Trap
        dup_check = manifest.is_duplicate_card(role, sd_cid)
        if dup_check and not force_duplicate:
            dup_role, dup_info = dup_check
            manifests.duplicate_detected = True
            manifests.duplicates.append((uuid_hex, role, dup_info))
            print("\n==================================================================")
            print("   [!] ERROR: DUPLICATE CARD DETECTED!")
            print("==================================================================")
            print(f"The card currently mounted at: {source_dir}")
            print(f"has Role: '{role}' (Node {node_id}, CID: {sd_cid or 'unknown'})")
            print(f"which was ALREADY INGESTED for Sortie: {uuid_hex}")
            print(f"at timestamp: {dup_info.get('ingested_at', 'unknown')} by '{dup_info.get('offloader_user', 'unknown')}'.")
            print(f"Files previously recorded: {dup_info.get('file_count', 0)} frames.")
            print("")
            print(f"Triad Status: PARTIAL ({len(manifest.data['cards_ingested'])}/3 Cards Ingested)")
            if manifest.data.get("missing_roles"):
                print(f"Still Waiting For: {', '.join(manifest.data['missing_roles'])}")
            print("")
            print("ACTION REQUIRED: Please unmount and remove this card, then insert")
            print("one of the remaining missing cards!")
            print("==================================================================\n")
            continue

        print(f"\nFound Sortie {dataset_folder(uuid_hex, sortie)} (mission {uuid_hex}):")
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

        # Atomic Verification Invariant: Ensure all files exist at destination and match source size
        all_verified = True
        for src_f in files:
            dst_f = os.path.join(byr_dest_dir, os.path.basename(src_f))
            if not os.path.exists(dst_f) or os.path.getsize(dst_f) != os.path.getsize(src_f):
                all_verified = False
                break

        if not all_verified:
            print(f"  [ERROR] Verification failed for Sortie {uuid_hex}! Not all files copied cleanly.", file=sys.stderr)
            continue

        # Compute segmented sequence ranges
        seq_ranges, dropped_seq_spans, seq_continuity = compute_seq_segments(seqs)

        # Mathematical Invariant check
        span_total = sum(end - start + 1 for start, end in seq_ranges)
        if span_total != len(files):
            print(f"  [WARN] Sequence span total ({span_total}) does not match file count ({len(files)})!", file=sys.stderr)

        # Emit dual offload receipts (on card and on host ledger)
        card_rcpt, host_rcpt, rcpt_data = emit_offload_receipt(
            source_sortie_dir=source_sortie_dir,
            dest_sortie_dir=sortie_dir,
            task_uuid=uuid_hex,
            role=role,
            node_id=node_id,
            bcm_cpu_serial=cpu_serial,
            sd_card_cid=sd_cid,
            file_count=len(files),
            seq_ranges=seq_ranges,
            dropped_seq_spans=dropped_seq_spans,
            seq_continuity=seq_continuity,
            source_mount=source_dir,
        )

        receipts_dict = {}
        if card_rcpt:
            receipts_dict["card"] = os.path.basename(card_rcpt)
        if host_rcpt:
            receipts_dict["host"] = host_rcpt

        # Capture session.log, .card_benchmark, and other diagnostic logs from this card
        copied_logs = find_and_copy_card_logs(source_dir, sortie_dir, role,
                                              dataset_folder(uuid_hex, sortie) if sortie else None)

        manifest.record_card_ingest(
            role=role,
            node_id=node_id,
            cpu_serial=cpu_serial,
            sd_cid=sd_cid,
            file_count=len(files),
            seq_min=min(seqs),
            seq_max=max(seqs),
            files_copied=copied_count,
            seq_ranges=seq_ranges,
            dropped_seq_spans=dropped_seq_spans,
            seq_continuity=seq_continuity,
            receipts=receipts_dict,
            offloader_user=rcpt_data.get("offloader_user"),
            logs=copied_logs,
        )
        manifest.print_status()

    # Sync OS disk buffers
    try:
        subprocess.run(["sync"], check=False)
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


def check_incomplete_exit_barrier(active_manifests: Dict[str, TriadManifest]) -> bool:
    """
    If any sortie is incomplete, prompts user with a high-visibility barrier.
    Returns True if user typed 'ABORT' to exit, or False to resume wizard.
    """
    if not active_manifests:
        return True

    all_complete = all(m.data["triad_complete"] for m in active_manifests.values())
    if all_complete:
        return True

    print("\n==================================================================")
    print("   [!] WARNING: TRIAD DE-ENROLLMENT IS INCOMPLETE!")
    print("==================================================================")
    for uuid_hex, m in active_manifests.items():
        if not m.data["triad_complete"]:
            ingested_str = ", ".join(m.data["cards_ingested"].keys()) or "None"
            missing_str = ", ".join(m.data["missing_roles"])
            print(f"Sortie UUID    : {uuid_hex}")
            print(f"Cards Ingested : {ingested_str} ({len(m.data['cards_ingested'])}/3)")
            print(f"MISSING ROLES  : {missing_str} ({len(m.data['missing_roles'])}/3 NOT OFFLOADED!)")
    print("")
    print("HAZARD: If you unmount and format the missing cards, their imagery")
    print("will be PERMANENTLY DESTROYED and the survey will be unrecoverable!")
    print("==================================================================")
    confirm = input("Type 'ABORT' to confirm premature exit with missing cards,\nor press [Enter] to continue offloading: ").strip()
    return confirm == "ABORT"


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
        try:
            print(f"\n>>> [Card {card_step}] Please insert and mount SD card {card_step} of 3.")
            user_in = input("Press [Enter] once the card is mounted (or type 'q' to finish): ").strip()
            if user_in.lower() == 'q':
                if not check_incomplete_exit_barrier(active_manifests):
                    continue
                break

            # Look for mounted cards
            mounts = find_sdcard_mounts()
            if not mounts:
                user_path = input("No automount detected. Enter path to mounted card (e.g. /media/user/imagery): ").strip()
                if user_path.lower() == 'q':
                    if not check_incomplete_exit_barrier(active_manifests):
                        continue
                    break
                elif user_path and os.path.isdir(user_path):
                    mounts = [user_path]
                else:
                    print("Invalid path or no card found. Retrying...")
                    continue

            source_path = mounts[0]
            print(f"Using card at: {source_path}")

            manifests = de_enroll_card(source_path, dest_root, auto_unmount=auto_unmount)

            if manifests.duplicate_detected:
                print(f"Notice: Duplicate card ignored for Step {card_step}. Please insert next card.")
                continue

            active_manifests.update(manifests)

            # Check if all sorties have complete triads
            all_complete = bool(active_manifests) and all(m.data["triad_complete"] for m in active_manifests.values())

            if all_complete:
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
                if not check_incomplete_exit_barrier(active_manifests):
                    continue
                break
            card_step += 1

        except KeyboardInterrupt:
            print("\n")
            if not check_incomplete_exit_barrier(active_manifests):
                continue
            break


def audit_card(source_dir: str):
    """
    Scans a mounted SD card directory and prints an audit report of all sorties,
    their .byr file counts, and any .offload_receipt_*.json receipts found.
    """
    print("==================================================================")
    print("   Tri-Cam MicroSD Card Offload Audit Report                      ")
    print("==================================================================")
    print(f"Card Path: {os.path.abspath(source_dir)}")

    sorties = scan_source_card(source_dir)
    if not sorties:
        print("No .byr imagery found on this media.")
        print("Safe to Wipe: YES (Card is blank / contains no survey imagery)")
        print("==================================================================")
        return

    all_safe_to_wipe = True

    for key, info in sorties.items():
        uuid_hex = info.get("task_uuid", key)
        sortie = info.get("sortie_id")
        role = info["role"]
        node_id = info["node_id"]
        files = info["files"]
        seqs = info["seqs"]
        sd_cid = info["sd_card_cid"]
        source_sortie_dir = info.get("source_sortie_dir") or source_dir

        seq_ranges, dropped, continuity = compute_seq_segments(seqs)

        print(f"\nSortie UUID : {uuid_hex}")
        print(f"  Role      : {role} (Node {node_id}) | CID: {sd_cid or 'unknown'}")
        print(f"  Files     : {len(files)} .byr frames on disk (Continuity: {continuity})")
        if dropped:
            print(f"  Drop Spans: {dropped}")

        # Search for receipts in this sortie directory
        receipt_files = sorted(glob.glob(os.path.join(source_sortie_dir, ".offload_receipt_*.json")))
        valid_receipts = []

        for rf in receipt_files:
            try:
                with open(rf, "r") as f:
                    rdata = json.load(f)
                if rdata.get("status") == "VERIFIED_COMPLETE" and rdata.get("file_count") == len(files):
                    valid_receipts.append((rf, rdata))
            except Exception:
                pass

        if valid_receipts:
            print(f"  Receipts  : {len(valid_receipts)} valid matching receipt(s) found:")
            for rf, rdata in valid_receipts:
                r_ts = rdata.get("offloaded_at_utc", "unknown")
                r_user = rdata.get("offloader_user", "unknown")
                r_host = rdata.get("offloader_host", "unknown")
                r_dest = rdata.get("destination_path", "unknown")
                print(f"    • {os.path.basename(rf)}: Offloaded at {r_ts} by '{r_user}@{r_host}'")
                print(f"      Destination: {r_dest}")
            print("  Safe to Wipe: YES (Verified offloaded)")
        else:
            print("  Receipts  : [!] NO VALID MATCHING OFFLOAD RECEIPT FOUND!")
            if receipt_files:
                print(f"    (Found {len(receipt_files)} receipt(s), but file counts or status did not match disk!)")
            print("  Safe to Wipe: NO - UN-OFFLOADED IMAGERY AT RISK!")
            all_safe_to_wipe = False

    print("\n==================================================================")
    print(f"Overall Card Status: {'SAFE TO WIPE' if all_safe_to_wipe else 'DO NOT WIPE (Un-offloaded imagery present!)'}")
    print("==================================================================")


def list_host_receipts():
    """
    Lists all receipts recorded in ~/.tri-cam-receipts/.
    """
    print("==================================================================")
    print("   Local Workstation Offload Ledger (~/.tri-cam-receipts)         ")
    print("==================================================================")
    if not os.path.isdir(RECEIPTS_DIR):
        print(f"No receipts found. Directory does not exist: {RECEIPTS_DIR}")
        print("==================================================================")
        return

    receipt_files = sorted(glob.glob(os.path.join(RECEIPTS_DIR, "*.json")))
    if not receipt_files:
        print(f"No receipts cataloged in: {RECEIPTS_DIR}")
        print("==================================================================")
        return

    receipts_by_uuid = {}
    for rf in receipt_files:
        try:
            with open(rf, "r") as f:
                rdata = json.load(f)
            u = rdata.get("task_uuid", "unknown")
            receipts_by_uuid.setdefault(u, []).append(rdata)
        except Exception:
            pass

    print(f"{'Sortie UUID':<34} {'Role':<12} {'Files':<6} {'Offloaded At (UTC)':<20} {'User@Host':<22}")
    print("-" * 100)

    complete_triads = 0
    total_receipts = 0

    for u, rlist in receipts_by_uuid.items():
        roles_seen = set()
        for r in rlist:
            total_receipts += 1
            role = r.get("role", "unknown")
            roles_seen.add(role)
            fc = r.get("file_count", 0)
            ts = r.get("offloaded_at_utc", "unknown")
            uh = f"{r.get('offloader_user','?')[:10]}@{r.get('offloader_host','?')[:10]}"
            print(f"{u:<34} {role:<12} {fc:<6} {ts:<20} {uh:<22}")
        if set(EXPECTED_ROLES).issubset(roles_seen):
            complete_triads += 1

    print("-" * 100)
    print(f"Total Receipts: {total_receipts} | Unique Sorties: {len(receipts_by_uuid)} | Complete Triads: {complete_triads}")
    print("==================================================================")


def main():
    parser = argparse.ArgumentParser(description="Tri-Cam SD Card Triad De-Enrollment Tool")
    parser.add_argument("--source", "-s", help="Path to mounted SD card directory (e.g. /mnt/sd_imagery)")
    parser.add_argument("--dest", "-d", default="triad_datasets", help="Destination root directory for sorties")
    parser.add_argument("--wizard", "-w", action="store_true", help="Launch interactive 3-card insertion wizard")
    parser.add_argument("--unmount", "-u", action="store_true", help="Safely unmount SD card after copying")
    parser.add_argument("--audit-card", "-a", help="Scan and audit a mounted SD card for offload receipts without copying")
    parser.add_argument("--list-receipts", "-l", action="store_true", help="List all receipts in host ledger (~/.tri-cam-receipts/)")
    parser.add_argument("--force-duplicate", action="store_true", help="Allow re-ingesting a card that was already offloaded")

    args = parser.parse_args()

    if args.list_receipts:
        list_host_receipts()
    elif args.audit_card:
        audit_card(args.audit_card)
    elif args.wizard or not args.source:
        # If no source provided, default to wizard mode
        interactive_wizard(args.dest, auto_unmount=args.unmount)
    else:
        de_enroll_card(args.source, args.dest, auto_unmount=args.unmount, force_duplicate=args.force_duplicate)


if __name__ == "__main__":
    main()
