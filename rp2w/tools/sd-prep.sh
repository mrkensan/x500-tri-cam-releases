#!/usr/bin/env bash
set -e

# ==============================================================================
# RP2W SD Card End-to-End Preparation Tool (Production Releases)
#
# Partitions, formats with flash-aligned geometry, and provisions the
# Alpine Linux OS, kernel boot configurations, and production overlay
# onto a target MicroSD card for use in the Raspberry Pi Zero 2W nodes.
#
# Requirements: parted dosfstools exfatprogs wipefs tar sha256sum (curl or wget)
# ==============================================================================

if [ "$EUID" -ne 0 ]; then
  echo "Error: Must be run as root (e.g., sudo ./rp2w/tools/sd-prep.sh /dev/sdb)"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RP2W_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$RP2W_DIR/.." && pwd)"
DOWNLOADS_DIR="$REPO_ROOT/downloads"

DISK=""
AUTO_CONFIRM=0
RELEASE_TAG="latest"
RELEASE_SPECIFIED=0

ALPINE_URL="https://dl-cdn.alpinelinux.org/alpine/v3.24/releases/aarch64/alpine-rpi-3.24.1-aarch64.tar.gz"
EXPECTED_SHA256="f50672e626f234e13686eb7534292e5b7c0a639986d8afd87c25526bc7a75882"
TARBALL="$DOWNLOADS_DIR/alpine-rpi-3.24.1-aarch64.tar.gz"

while [ $# -gt 0 ]; do
  case "$1" in
    -y|--yes)
      AUTO_CONFIRM=1
      shift
      ;;
    --release)
      if [ -n "$2" ] && [[ "$2" != -* ]]; then
        RELEASE_TAG="$2"
        RELEASE_SPECIFIED=1
        shift 2
      else
        echo "Error: --release requires a release name or version tag (e.g. latest, r50)"
        exit 1
      fi
      ;;
    -*)
      echo "Unknown option: $1"
      echo "Usage: sudo $0 <block_device> [-y|--yes] [--release <name>]"
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
  echo "Usage: sudo $0 <block_device> [-y|--yes] [--release <name>]"
  echo "Example: sudo $0 /dev/sdb"
  echo "         sudo $0 /dev/mmcblk0 --yes --release latest"
  exit 1
fi


# 0. Ensure base Alpine Linux tarball is available (download & verify if missing)
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
RELEASE_DIR="$RP2W_DIR/releases/$RELEASE_TAG"
OVERLAY_SHA_DISPLAY=""

if [ ! -d "$RELEASE_DIR" ]; then
  echo "Error: Release directory not found: $RELEASE_DIR"
  echo "Available releases in $RP2W_DIR/releases/:"
  ls -la "$RP2W_DIR/releases/" 2>/dev/null || echo "  (none)"
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
  if [ -L "$RP2W_DIR/releases/latest" ]; then
    RESOLVED_TARGET=$(readlink "$RP2W_DIR/releases/latest")
  fi
  if [ -n "$RESOLVED_TARGET" ]; then
    RELEASE_TITLE="latest -> $RESOLVED_TARGET (Default Production Release)"
  else
    RELEASE_TITLE="latest (Default Production Release)"
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

if [ "$AUTO_CONFIRM" -ne 1 ]; then
  echo "WARNING: ALL DATA ON $DISK WILL BE PERMANENTLY DESTROYED!"
  read -p "Type 'YES' to continue: " CONFIRM
  if [ "$CONFIRM" != "YES" ]; then
    echo "Aborted by user."
    exit 1
  fi
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

echo "  -> Partition 1: FAT32 (PIBOOT)..."
mkfs.vfat -F 32 -n PIBOOT "$PART1"

echo "  -> Partition 2: exFAT (imagery) [2MB clusters, 16MB flash boundary, packed bitmap]..."
mkfs.exfat -F -n imagery -c 2M -b 16M --pack-bitmap "$PART2"

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
