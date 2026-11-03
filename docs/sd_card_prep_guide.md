# MicroSD Card Preparation & Provisioning Guide

This guide details how to partition, format, and provision MicroSD cards for the Raspberry Pi Zero 2W compute nodes in the GCC X500 Tri-Cam photogrammetry payload.

---

## 1. The "Bin of Cards" Concept

In production photogrammetry operations, cards operate in a universal pool:
1. **Universal Image:** The exact same software image is flashed to every MicroSD card.
2. **Hardware Strapping:** When inserted into a carrier socket, the Pi reads physical strapping pins (`GP23/GP24`) to automatically assume its role (`Nadir`, `ObliqueRt`, or `ObliqueFwd`).
3. **Card Interchangeability:** Any card taken from the bin can be placed into any socket on the airframe without manual reconfiguration.

---

## 2. Requirements & Prerequisites

### Recommended Card Hardware
- High-endurance or V30/A2 rated MicroSD cards (e.g. SanDisk Extreme, Samsung PRO Plus).
- Capacities: 64 GB, 128 GB, 256 GB, or 512 GB.

### Host Dependencies
The preparation script uses standard Linux partition and filesystem utilities:
- `parted`
- `dosfstools` (for `mkfs.vfat`)
- `exfatprogs` (for `mkfs.exfat` with packed bitmap support)
- `wipefs`
- `tar`
- `curl` or `wget`

On Debian/Ubuntu systems, install missing tools via:
```bash
sudo apt update
sudo apt install -y parted dosfstools exfatprogs util-linux tar curl
```

---

## 3. Partition Architecture & Alignment

The provisioner formats each card with two partitions aligned to physical 16 MB flash erase blocks:

```text
┌──────────────────────┬────────────────────────────────────────────────────────┐
│  Partition 1: PIBOOT │  Partition 2: imagery                                  │
│  FAT32 (512 MB)      │  exFAT (Remainder of card)                             │
│  Kernel, overlays,   │  2MB clusters, 16MB flash-erase alignment              │
│  boot configs        │  Stores raw .byr captures & sortie logs                │
└──────────────────────┴────────────────────────────────────────────────────────┘
```

1. **Partition 1 (`PIBOOT`, FAT32, ~508 MB):**
   - Active boot partition containing Alpine Linux kernel, initramfs, and `x500.apkovl.tar.gz`.
   - Contains `usercfg.txt` configured for 100 MHz SDIO clocking (`dtparam=sd_overclock=100`).
2. **Partition 2 (`imagery`, exFAT, remainder):**
   - High-throughput image capture partition formatted with **2 MB cluster size** and packed allocation bitmap to eliminate flash write-amplification and write stall hazards.

---

## 4. Execution Walkthrough

### Step 1: Identify Target Block Device
Insert the card into your reader and locate its device node:
```bash
lsblk
```
*Example: `/dev/sdb` (or `/dev/mmcblk0` on integrated laptop readers).*

> **SAFETY WARNING:** Double check your device node carefully. Running against the wrong disk will erase all data on that drive. The script actively prevents running on `/dev/sda`.

### Step 2: Run the Provisioner
From the root of this repository:
```bash
sudo ./rp2w/tools/sd-prep.sh /dev/sdb
```

### What Happens Automatically:
1. **OS Tarball Check:** If `downloads/alpine-rpi-3.24.1-aarch64.tar.gz` is not cached locally, it is downloaded from the official Alpine CDN and checked against its SHA-256 hash.
2. **Safety Prompt:** Shows the device model, size, and enrolled release details (`r50`), requiring manual `YES` confirmation (bypassable with `-y` for bulk card batches).
3. **Wipe & Partition:** Wipes existing headers and partitions with 16 MB boundary alignment.
4. **Filesystem Creation:** Formats `PIBOOT` (FAT32) and `imagery` (exFAT with 2 MB clusters).
5. **Release Installation:** Installs base Alpine Linux files, kernel configs, and the `r50` production overlay (`x500.apkovl.tar.gz`).

### Bulk Flashing Flag (`-y`)
When provisioning batches of cards from the bin:
```bash
sudo ./rp2w/tools/sd-prep.sh /dev/sdb -y
```

---

## 5. Post-Provisioning Verification

Upon completion, `lsblk` will display:
```text
NAME   LABEL   SIZE FSTYPE MOUNTPOINT
sdb           238.3G        
├─sdb1 PIBOOT   508M vfat   
└─sdb2 imagery 237.8G exfat  
```
Eject the card and it is immediately ready for insertion into any camera slot on the airframe.
