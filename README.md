# GCC X500 Tri-Cam Module - Official Releases

Welcome to the official production release repository for the **GCC X500 Tri-Cam Photogrammetry System**.

This repository hosts pre-compiled production firmware binaries, kernel boot configurations, turnkey card provisioning tools, and host-side image processing pipelines for field operations. No compilation tools or embedded toolchains are required to use these releases.

---

## Current Production Releases

| Subsystem | Target Hardware | Current Release | Key Capabilities |
|---|---|---|---|
| **[RP2W](rp2w/)** | 3× Raspberry Pi Zero 2W | `r50` | In-Survey AEC, Flash Exclusivity, 100MHz SDIO, Chronological Sorties |
| **[KB2040](kb2040/)** | Adafruit KB2040 (RP2040) | `r78` | Hardware Triggering, MAVLink v2, Fleet Version Consensus, Status LED |
| **[Image Pipeline](image_pipeline/)** | Host Workstation (Linux/macOS/Win) | `r1` | Triad De-Enrollment, Synchronized Ingest, RAW12 -> DNG v1.4 & JPEG |

---

## Quickstart Guide

### 1. Provisioning RP2W Compute Node MicroSD Cards
The RP2W system uses a universal OS image across all three channels (`Nadir`, `ObliqueRt`, `ObliqueFwd`). Channel identities are determined at boot via carrier-board hardware strapping pins.

Insert a MicroSD card into your card reader, identify its device node (e.g. `/dev/sdb`), and run:
```bash
sudo ./rp2w/tools/sd-prep.sh /dev/sdb --release latest
```
*(The tool will automatically download and verify the base Alpine Linux OS archive on first run, partition with 16MB flash alignment, and install the production release).*

For full instructions, see **[MicroSD Card Preparation Guide](docs/sd_card_prep_guide.md)**.

---

### 2. Flashing the KB2040 Airframe Orchestrator
Connect the KB2040 module via USB to your workstation and run the 1200-baud automated updater script:
```bash
sudo python3 ./kb2040/tools/flash_kb2040.py
```
*(The script connects to the active serial interface, issues an automated 1200-baud touch reset to switch the RP2040 into bootloader mode, mounts the drive, copies the production UF2 firmware, and automatically reboots the board).*

For full details, see **[KB2040 Flashing Guide](docs/kb2040_flashing_guide.md)**.

---

### 3. Post-Flight Imagery Ingestion & Processing
Install host dependencies (one-time setup):
```bash
pip install -r image_pipeline/requirements.txt
```

**Step A — De-enroll the 3-card flight triad:**
```bash
python3 image_pipeline/tools/de_enroll_triad.py --wizard --dest /path/to/project_data
```

**Step B — Convert raw Bayer imagery to Adobe DNG and JPEG:**
```bash
python3 image_pipeline/tools/byr_pipeline.py \
  --input /path/to/project_data/SORTIE_YYYYMMDD_HHMMSS \
  --output /path/to/processed_deliverables \
  --auto-ev \
  --workers 8
```

For complete workflow details, see **[Image Pipeline Processing Guide](docs/image_pipeline_guide.md)**.

---

## Detailed Guides & Documentation

- **[MicroSD Card Preparation Guide](docs/sd_card_prep_guide.md)** — Flash alignment, partition layout, and troubleshooting.
- **[KB2040 Flashing Guide](docs/kb2040_flashing_guide.md)** — USB reset methods and bootloader diagnostics.
- **[Image Pipeline Processing Guide](docs/image_pipeline_guide.md)** — Ingest options, DNG raw metadata, and JPEG rendering options.
- **[RP2W Release Notes](rp2w/RELEASE_NOTES.md)** — Revision history and technical changes for compute nodes.
- **[KB2040 Release Notes](kb2040/RELEASE_NOTES.md)** — Revision history and technical changes for the orchestrator.
- **[Image Pipeline Release Notes](image_pipeline/RELEASE_NOTES.md)** — Ingestion and processing tool release details.
