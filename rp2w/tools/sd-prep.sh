#!/usr/bin/env bash
set -e

# ==============================================================================
# RP2W SD Card End-to-End Preparation Tool
#
# Partitions, formats with flash-aligned geometry, and provisions the
# Alpine Linux OS, kernel boot configurations, and production overlay
# onto a target MicroSD card for use in the Raspberry Pi Zero 2W nodes.
#
# Requirements: parted dosfstools exfatprogs wipefs tar
# ==============================================================================

if [ "$EUID" -ne 0 ]; then
  echo "Error: Must be run as root (e.g., sudo ./scripts/sd-prep.sh /dev/sdb)"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ "$SCRIPT_DIR" == */Releases/rp2w/tools* ]]; then
  RP2W_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
  REPO_ROOT="$(cd "$RP2W_DIR/.." && pwd)"
  RELEASES_DIR="$RP2W_DIR/releases"
  DOWNLOADS_DIR="$REPO_ROOT/downloads"
else
  REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
  RELEASES_DIR="$REPO_ROOT/releases"
  DOWNLOADS_DIR="$REPO_ROOT/downloads"
fi

DISK=""
AUTO_CONFIRM=0
REBUILD_OVERLAY=0
RELEASE_TAG="latest"
RELEASE_SPECIFIED=0
FORCE_WIPE_UNOFFLOADED=0

while [ $# -gt 0 ]; do
  case "$1" in
    -y|--yes)
      AUTO_CONFIRM=1
      shift
      ;;
    -r|--rebuild)
      REBUILD_OVERLAY=1
      shift
      ;;
    --release)
      if [ -n "$2" ] && [[ "$2" != -* ]]; then
        RELEASE_TAG="$2"
        RELEASE_SPECIFIED=1
        shift 2
      else
        echo "Error: --release requires a release name or version tag (e.g. latest, r44)"
        exit 1
      fi
      ;;
    --force-wipe-unoffloaded)
      FORCE_WIPE_UNOFFLOADED=1
      shift
      ;;
    -*)
      echo "Unknown option: $1"
      echo "Usage: sudo $0 <block_device> [-y|--yes] [-r|--rebuild] [--release <name>] [--force-wipe-unoffloaded]"
      exit 1
      ;;
    *)
      if [ -z "$DISK" ]; then
        DISK="$1"
      else
        echo "Unexpected argument: $1"
        exit 1
      fi
      shift
      ;;
  esac
done

if [ -z "$DISK" ] || [ ! -b "$DISK" ]; then
  echo "Usage: sudo $0 <block_device> [-y|--yes] [-r|--rebuild] [--release <name>] [--force-wipe-unoffloaded]"
  echo "Example: sudo $0 /dev/sdb"
  echo "         sudo $0 /dev/mmcblk0 --yes --release latest"
  exit 1
fi

# ==============================================================================
# Robust Safety Checks: Protect system root, boot, home, and swap partitions
# ==============================================================================

TARGET_CANONICAL=$(readlink -f "$DISK")

# 1. Identify all parent block devices backing active critical system mount points
CRITICAL_MOUNTS=("/" "/boot" "/boot/efi" "/home" "/var" "/usr")
for mnt in "${CRITICAL_MOUNTS[@]}"; do
  dev_src=$(findmnt -n -o SOURCE "$mnt" 2>/dev/null || true)
  if [ -n "$dev_src" ]; then
    dev_canon=$(readlink -f "$dev_src")
    pk=$(lsblk -no PKNAME "$dev_canon" 2>/dev/null | head -n1 || true)
    if [ -n "$pk" ]; then
      dev_disk_canon=$(readlink -f "/dev/$pk")
    else
      dev_disk_canon="$dev_canon"
    fi
    if [ "$TARGET_CANONICAL" = "$dev_disk_canon" ]; then
      echo "FATAL: $DISK is the active host system disk (hosts '$mnt' on $dev_src)!"
      echo "Refusing to execute to prevent system destruction."
      exit 1
    fi
  fi
done

# 2. Check active host swap partitions
while read -r swap_path rest; do
  if [[ "$swap_path" == /dev/* ]]; then
    swap_canon=$(readlink -f "$swap_path")
    pk=$(lsblk -no PKNAME "$swap_canon" 2>/dev/null | head -n1 || true)
    [ -n "$pk" ] && swap_disk_canon=$(readlink -f "/dev/$pk") || swap_disk_canon="$swap_canon"
    if [ "$TARGET_CANONICAL" = "$swap_disk_canon" ]; then
      echo "FATAL: $DISK is used by active host swap ($swap_path)!"
      echo "Refusing to execute."
      exit 1
    fi
  fi
done < <(tail -n +2 /proc/swaps 2>/dev/null || true)

# 3. Check if any partition on the target device is currently mounted to a critical mount
for mnt in $(lsblk -lno MOUNTPOINTS "$TARGET_CANONICAL" 2>/dev/null | grep -v '^$'); do
  for crit in "${CRITICAL_MOUNTS[@]}"; do
    if [ "$mnt" = "$crit" ]; then
      echo "FATAL: $DISK has an active partition mounted at critical system path '$mnt'!"
      exit 1
    fi
  done
done

# 4. Non-removable internal drive protection
IS_REMOVABLE=$(lsblk -dno RM "$TARGET_CANONICAL" 2>/dev/null || echo "1")
TRAN_TYPE=$(lsblk -dno TRAN "$TARGET_CANONICAL" 2>/dev/null || echo "unknown")

if [ "$IS_REMOVABLE" = "0" ] && [[ "$TRAN_TYPE" =~ ^(sata|nvme|ata)$ ]] && [ "$AUTO_CONFIRM" -ne 1 ]; then
  echo ""
  echo "=========================================================="
  echo "WARNING: $DISK is detected as an internal fixed disk (TRAN=$TRAN_TYPE, RM=0)."
  echo "Standard MicroSD cards typically appear as removable USB or MMC media."
  echo "=========================================================="
  read -p "Type 'I_KNOW_THIS_IS_CORRECT' to proceed: " INTERNAL_CONFIRM
  if [ "$INTERNAL_CONFIRM" != "I_KNOW_THIS_IS_CORRECT" ]; then
    echo "Aborted by user."
    exit 1
  fi
fi

ALPINE_URL="https://dl-cdn.alpinelinux.org/alpine/v3.24/releases/aarch64/alpine-rpi-3.24.1-aarch64.tar.gz"
EXPECTED_SHA256="f50672e626f234e13686eb7534292e5b7c0a639986d8afd87c25526bc7a75882"
DOWNLOADS_DIR="$REPO_ROOT/downloads"
TARBALL="$DOWNLOADS_DIR/alpine-rpi-3.24.1-aarch64.tar.gz"

if [ ! -f "$TARBALL" ]; then
  echo "Base Alpine Linux tarball not found at $TARBALL"
  echo "Downloading Alpine Linux 3.24.1 aarch64 from official CDN..."
  mkdir -p "$DOWNLOADS_DIR"
  if command -v curl &>/dev/null; then
    curl -L --progress-bar -o "$TARBALL" "$ALPINE_URL"
  elif command -v wget &>/dev/null; then
    wget --show-progress -O "$TARBALL" "$ALPINE_URL"
  else
    echo "Error: Neither curl nor wget found. Please download $ALPINE_URL to $TARBALL manually."
    exit 1
  fi

  echo "Verifying Alpine Linux SHA-256 checksum..."
  ACTUAL_SHA256=$(sha256sum "$TARBALL" | awk '{print $1}')
  if [ "$ACTUAL_SHA256" != "$EXPECTED_SHA256" ]; then
    echo "Error: SHA-256 checksum mismatch on downloaded Alpine Linux archive!"
    echo "  Expected: $EXPECTED_SHA256"
    echo "  Received: $ACTUAL_SHA256"
    rm -f "$TARBALL"
    exit 1
  fi
  echo "Checksum verified: $ACTUAL_SHA256"
fi

# Resolve and advertise release target before confirmation
RELEASE_DIR="$RELEASES_DIR/$RELEASE_TAG"
OVERLAY_SHA_DISPLAY=""

if [ "$REBUILD_OVERLAY" -eq 1 ]; then
  RELEASE_TITLE="Rebuild from Source (via scripts/enroll-release.sh)"
  BUILD_DATE_DISPLAY="(Will be compiled and enrolled from working tree)"
else
  if [ ! -d "$RELEASE_DIR" ]; then
    echo "Error: Release directory not found: $RELEASE_DIR"
    echo "Available releases in $RELEASES_DIR/:"
    ls -la "$RELEASES_DIR/" 2>/dev/null || echo "  (none)"
    echo "Use -r / --rebuild to compile and enroll a new release first."
    exit 1
  fi

  APKOVL="$RELEASE_DIR/x500.apkovl.tar.gz"
  USERCFG="$RELEASE_DIR/usercfg.txt"
  CMDLINE="$RELEASE_DIR/cmdline.txt"

  if [ ! -f "$APKOVL" ] || [ ! -f "$USERCFG" ] || [ ! -f "$CMDLINE" ]; then
    echo "Error: Missing required release artifacts in $RELEASE_DIR:"
    [ ! -f "$APKOVL" ] && echo "  - Missing $APKOVL"
    [ ! -f "$USERCFG" ] && echo "  - Missing $USERCFG"
    [ ! -f "$CMDLINE" ] && echo "  - Missing $CMDLINE"
    exit 1
  fi

  if [ "$RELEASE_SPECIFIED" -eq 0 ]; then
    RESOLVED_TARGET=""
    if [ -L "$RELEASES_DIR/latest" ]; then
      RESOLVED_TARGET=$(readlink "$RELEASES_DIR/latest")
    fi
    if [ -n "$RESOLVED_TARGET" ]; then
      RELEASE_TITLE="latest -> $RESOLVED_TARGET (Default Enrolled Release)"
    else
      RELEASE_TITLE="latest (Default Enrolled Release)"
    fi
  else
    RELEASE_TITLE="$RELEASE_TAG (Specified via CLI)"
  fi

  MANIFEST_FILE="$RELEASE_DIR/release_manifest.json"
  if [ -f "$MANIFEST_FILE" ]; then
    MANIFEST_DATE=$(grep '"build_timestamp"' "$MANIFEST_FILE" | sed -E 's/.*"build_timestamp": *"([^"]+)".*/\1/')
    MANIFEST_COMMIT=$(grep '"git_commit"' "$MANIFEST_FILE" | sed -E 's/.*"git_commit": *"([^"]+)".*/\1/')
    MANIFEST_REV=$(grep '"commit_count"' "$MANIFEST_FILE" | sed -E 's/.*"commit_count": *([0-9]+).*/\1/')
    MANIFEST_SHA=$(grep '"overlay_sha256"' "$MANIFEST_FILE" | sed -E 's/.*"overlay_sha256": *"([^"]+)".*/\1/')
    BUILD_DATE_DISPLAY="$MANIFEST_DATE (r$MANIFEST_REV-$MANIFEST_COMMIT)"
    OVERLAY_SHA_DISPLAY="$MANIFEST_SHA"
  else
    BUILD_DATE_DISPLAY=$(stat -c '%y' "$APKOVL" 2>/dev/null || date -r "$APKOVL" 2>/dev/null || echo "Unknown")
    OVERLAY_SHA_DISPLAY=$(sha256sum "$APKOVL" 2>/dev/null | awk '{print $1}')
  fi
fi

echo "=========================================================="
echo "       RP2W MicroSD Card End-to-End Preparation           "
echo "=========================================================="
echo "Target Device   : $DISK"
echo "Device Details  :"
lsblk -d -o NAME,MODEL,SIZE,TRAN,SERIAL "$DISK" 2>/dev/null || lsblk -d "$DISK"
echo ""
echo "Provisioning Release:"
echo "  Target Release : $RELEASE_TITLE"
echo "  Build Date     : $BUILD_DATE_DISPLAY"
if [ -n "$OVERLAY_SHA_DISPLAY" ]; then
  echo "  Overlay SHA256 : $OVERLAY_SHA_DISPLAY"
fi
echo "=========================================================="
echo ""

# ==============================================================================
# Pre-Wipe Data Safety & Un-Offloaded Imagery Audit
# Inspects existing partitions on target device to verify that all .byr files
# have matching offload receipts (.offload_receipt_*.json).
# ==============================================================================

echo "Auditing target device for un-offloaded aerial survey imagery..."
UNOFFLOADED_DETECTED=0
AUDIT_FAILURE_REPORT=""
AUDIT_SUCCESS_REPORT=""

for part_name in $(lsblk -lno NAME "$DISK" 2>/dev/null | tail -n +2); do
  part_dev="/dev/$part_name"
  [ -b "$part_dev" ] || continue

  INSPECT_MNT=$(mktemp -d /tmp/sd_prep_inspect_XXXXXX)

  if mount -o ro "$part_dev" "$INSPECT_MNT" 2>/dev/null; then
    PY_AUDIT_OUTPUT=$(python3 - "$INSPECT_MNT" "$part_dev" <<'EOF'
import os, sys, glob, json

inspect_root = sys.argv[1]
part_dev = sys.argv[2]

byr_files = glob.glob(os.path.join(inspect_root, "**", "*.byr"), recursive=True)
if not byr_files:
    sys.exit(0)

dirs_with_byr = sorted(set(os.path.dirname(os.path.abspath(f)) for f in byr_files))

unoffloaded = []
verified = []

for d in dirs_with_byr:
    f_count = len(glob.glob(os.path.join(d, "*.byr")))
    receipts = sorted(glob.glob(os.path.join(d, ".offload_receipt_*.json")))

    matched = None
    for rf in receipts:
        try:
            with open(rf, "r") as r_f:
                r_data = json.load(r_f)
            if r_data.get("status") == "VERIFIED_COMPLETE" and r_data.get("file_count") == f_count:
                matched = r_data
                break
        except Exception:
            pass

    rel_d = os.path.relpath(d, inspect_root)
    if matched:
        u = matched.get("offloader_user", "unknown")
        h = matched.get("offloader_host", "unknown")
        ts = matched.get("offloaded_at_utc", "unknown")
        dst = matched.get("destination_path", "unknown")
        verified.append(f"    • [VERIFIED] {rel_d} ({f_count} frames) on {part_dev}\n      Offloaded by '{u}@{h}' at {ts}\n      Destination: {dst}")
    else:
        unoffloaded.append(f"    • [UN-OFFLOADED] {rel_d} ({f_count} frames) on {part_dev} (NO VALID RECEIPT!)")

if verified:
    print("VERIFIED_ITEMS:")
    for v in verified:
        print(v)

if unoffloaded:
    print("UNOFFLOADED_ITEMS:")
    for u in unoffloaded:
        print(u)
    sys.exit(2)

sys.exit(0)
EOF
)
    PY_STATUS=$?
    umount "$INSPECT_MNT" 2>/dev/null || true
    rmdir "$INSPECT_MNT" 2>/dev/null || true

    if [ "$PY_STATUS" -eq 2 ]; then
      UNOFFLOADED_DETECTED=1
      AUDIT_FAILURE_REPORT="${AUDIT_FAILURE_REPORT}${PY_AUDIT_OUTPUT}\n"
    elif [ -n "$PY_AUDIT_OUTPUT" ]; then
      AUDIT_SUCCESS_REPORT="${AUDIT_SUCCESS_REPORT}${PY_AUDIT_OUTPUT}\n"
    fi
  else
    rmdir "$INSPECT_MNT" 2>/dev/null || true
  fi
done

if [ "$UNOFFLOADED_DETECTED" -eq 1 ]; then
  echo ""
  echo "=========================================================="
  echo "FATAL: UN-OFFLOADED AERIAL SURVEY IMAGERY DETECTED!"
  echo "=========================================================="
  echo -e "$AUDIT_FAILURE_REPORT"
  echo "Refusing to wipe $DISK to prevent permanent photogrammetry data loss."
  echo "Please offload this card using 'de_enroll_triad.py' first."
  echo "=========================================================="
  if [ "$FORCE_WIPE_UNOFFLOADED" -eq 1 ]; then
    echo "WARNING: --force-wipe-unoffloaded specified. Overriding safety block!"
    echo "=========================================================="
    echo ""
  else
    echo "(To intentionally destroy this imagery and force wipe, re-run with: --force-wipe-unoffloaded)"
    echo ""
    exit 1
  fi
elif [ -n "$AUDIT_SUCCESS_REPORT" ]; then
  echo ""
  echo "[PASS] Pre-Wipe Data Safety Audit:"
  echo -e "$AUDIT_SUCCESS_REPORT"
  echo "All imagery on $DISK verified offloaded. Safe to wipe."
  echo ""
else
  echo "[PASS] No survey imagery found on $DISK (card is blank or already formatted)."
  echo ""
fi

if [ "$AUTO_CONFIRM" -ne 1 ]; then
  echo "WARNING: ALL DATA ON $DISK WILL BE PERMANENTLY DESTROYED!"
  read -p "Type 'YES' to continue: " CONFIRM
  if [ "$CONFIRM" != "YES" ]; then
    echo "Aborted by user."
    exit 1
  fi
fi

# 1. Resolve release artifacts (zero-compilation field mode or dev rebuild)
if [ "$REBUILD_OVERLAY" -eq 1 ]; then
  echo ""
  echo "[1/6] Rebuilding production release via scripts/enroll-release.sh..."
  "$REPO_ROOT/scripts/enroll-release.sh"
  RELEASE_DIR="$RELEASES_DIR/$RELEASE_TAG"
  APKOVL="$RELEASE_DIR/x500.apkovl.tar.gz"
  USERCFG="$RELEASE_DIR/usercfg.txt"
  CMDLINE="$RELEASE_DIR/cmdline.txt"
fi

echo ""
echo "[1/6] Verified release artifacts in: $RELEASE_DIR"
echo "  -> Overlay : $(basename "$APKOVL")"
echo "  -> Config  : $(basename "$USERCFG")"
echo "  -> Cmdline : $(basename "$CMDLINE")"

# 2. Unmount all partitions on target device
echo ""
echo "[2/6] Unmounting any active partitions on $DISK..."
for part in $(lsblk -lno NAME "$DISK" | tail -n +2); do
  umount "/dev/$part" 2>/dev/null || true
  udisksctl unmount -b "/dev/$part" 2>/dev/null || true
done
sync
sleep 1

# 3. Wipe partition table and filesystem signatures
echo ""
echo "[3/6] Wiping partition table and filesystem signatures..."
wipefs --all --force "$DISK"

# 4. Create MBR partition table with physical flash boundary alignment
#    - Partition 1: FAT32 (PIBOOT), 4MiB to 512MiB (Active Boot)
#    - Partition 2: exFAT (imagery), 512MiB to 100% (Aligned on 16MB boundary)
echo ""
echo "[4/6] Partitioning disk with 16MB flash-erase alignment..."
parted -s -a optimal "$DISK" mklabel msdos
parted -s -a optimal "$DISK" mkpart primary fat32 4MiB 512MiB
parted -s "$DISK" set 1 boot on
parted -s -a optimal "$DISK" mkpart primary 512MiB 100%

# Force kernel to re-read partition table
partprobe "$DISK"
sleep 2

# Resolve partition device nodes (/dev/sdX1 vs /dev/mmcblkXp1)
if [[ "$DISK" =~ [0-9]$ ]]; then
  PART1="${DISK}p1"
  PART2="${DISK}p2"
else
  PART1="${DISK}1"
  PART2="${DISK}2"
fi

# Wait for partition nodes to appear
for i in {1..5}; do
  if [ -b "$PART1" ] && [ -b "$PART2" ]; then
    break
  fi
  sleep 1
done

if [ ! -b "$PART1" ] || [ ! -b "$PART2" ]; then
  echo "Error: Partition block devices $PART1 or $PART2 did not appear."
  exit 1
fi

# 5. Format filesystems
echo ""
echo "[5/6] Formatting filesystems..."
umount "$PART1" "$PART2" 2>/dev/null || true
udisksctl unmount -b "$PART1" 2>/dev/null || true
udisksctl unmount -b "$PART2" 2>/dev/null || true

# Erase partition-level signatures and zero first 16MB of each partition
# This eliminates "Device has existing signatures. Refusing to overwrite" in exfatprogs >= 1.4
echo "  -> Wiping partition signatures and zeroing boundary sectors..."
wipefs --all --force "$PART1" 2>/dev/null || true
wipefs --all --force "$PART2" 2>/dev/null || true
dd if=/dev/zero of="$PART1" bs=1M count=4 status=none conv=fsync 2>/dev/null || true
dd if=/dev/zero of="$PART2" bs=1M count=16 status=none conv=fsync 2>/dev/null || true

partprobe "$DISK"
sleep 1

echo "  -> Partition 1: FAT32 (PIBOOT)..."
mkfs.vfat -F 32 -n PIBOOT "$PART1"

echo "  -> Partition 2: exFAT (imagery) [2MB clusters, 16MB flash boundary, packed bitmap]..."
EXFAT_FORCE=""
if mkfs.exfat --help 2>&1 | grep -q -- '-F'; then
  EXFAT_FORCE="-F"
fi
mkfs.exfat $EXFAT_FORCE -n imagery -c 2M -b 16M --pack-bitmap "$PART2"

# 6. Populate Boot / OS Partition
echo ""
echo "[6/6] Populating boot partition ($PART1)..."
MOUNT_POINT="/mnt/piboot_prep"
mkdir -p "$MOUNT_POINT"

cleanup() {
  sync
  umount "$MOUNT_POINT" 2>/dev/null || true
  rmdir "$MOUNT_POINT" 2>/dev/null || true
}
trap cleanup EXIT

mount "$PART1" "$MOUNT_POINT"

echo "  -> Extracting base Alpine Linux files..."
tar --no-same-owner -xf "$TARBALL" -C "$MOUNT_POINT"

echo "  -> Installing kernel boot configuration (usercfg.txt, cmdline.txt)..."
cp "$USERCFG" "$MOUNT_POINT/usercfg.txt"
cp "$CMDLINE" "$MOUNT_POINT/cmdline.txt"

echo "  -> Installing pre-compiled production overlay (x500.apkovl.tar.gz)..."
cp "$APKOVL" "$MOUNT_POINT/x500.apkovl.tar.gz"

if [ -f "$RELEASE_DIR/release_manifest.json" ]; then
  cp "$RELEASE_DIR/release_manifest.json" "$MOUNT_POINT/release_manifest.json"
fi

sync
echo "  -> Sync complete. Unmounting..."
umount "$MOUNT_POINT"
rmdir "$MOUNT_POINT" 2>/dev/null || true
trap - EXIT

echo ""
echo "=========================================================="
echo "    SDCard Preparation Complete!                          "
echo "=========================================================="
echo "Final Disk Layout:"
lsblk -o NAME,LABEL,SIZE,FSTYPE,MOUNTPOINT "$DISK"
echo ""
echo "The card is fully configured for maximum 100MHz performance"
echo "and is ready to be inserted into an RP2W socket."
echo "=========================================================="
