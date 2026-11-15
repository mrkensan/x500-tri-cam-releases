# GCC X500 Tri-Cam Module - Official Releases

Welcome to the official production release repository for the **GCC X500 Tri-Cam Photogrammetry System**.

This repository hosts pre-compiled production firmware binaries, kernel boot configurations, turnkey card provisioning tools, and host-side image processing pipelines for field operations. No compilation tools or embedded toolchains are required to use these releases.

---

## Distributed artifacts

These are repository artifact pointers, not certification of the reconciled
2026-11-07 interfaces. The complete BYR V2, SDAT and mailbox contracts
require coordinated implementation/releases; see
[implementation status](../Tri-Cam%20Module/IMPLEMENTATION_STATUS.md).

| Subsystem | Target Hardware | Current Release | Key Capabilities |
|---|---|---|---|
| **[RP2W](rp2w/)** | 3× Raspberry Pi Zero 2W | `r93` (test release) | Plan-interface test release: cameras powered down at shutdown, full SD write speed, no fake frames. Use with KB2040 r191. Rollback: `r91`, `r86`, `r64` |
| **[KB2040](kb2040/)** | Adafruit KB2040 (RP2040) | `r191` (test release) | Plan interface (Tri-Cam plan header, Plan Loader installed by the Tri-Cam), exposure settle triggers, trigger line follows camera power. Use with RP2W r93. Rollback: `r183`, `r85` |
| **[Image Pipeline](image_pipeline/)** | Host Workstation (Linux/macOS/Win) | `r4` | Reads the test release's (RP2W r86) image files: offload by mission and sortie, RAW12/DPCM -> DNG v1.4 & JPEG. Rollback: `r2` |

**Test release 2026-11-14 (since 2026-11-15: KB2040 r191, RP2W r93):** read **[TEST_RELEASE_2026-11-14.md](TEST_RELEASE_2026-11-14.md)**
first: installing, plans (the sample plan and `tricam_plan.py stamp` / `validate` in
[`kb2040/tools/plan/`](kb2040/tools/plan/)), exposure behaviour, known limits and what is verified. Plans that use
Tri-Cam commands now need the Tri-Cam header; the flight controller's Plan Loader is installed by the Tri-Cam itself.

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
  --input /path/to/project_data/261107_1200_c7b8e1a0 \
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
