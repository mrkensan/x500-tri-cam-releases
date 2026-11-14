# Image Pipeline Processing Guide

This guide describes how to use the host-side Image Pipeline utilities to offload, organize, and convert raw `.byr` photogrammetry datasets captured by the GCC X500 Tri-Cam system.

The directory/verification examples describe the reconciled target workflow.
Current distributed scripts have not been certified against the new contracts;
see [implementation status](../../Tri-Cam%20Module/IMPLEMENTATION_STATUS.md)
and the [processing spec](../../Image%20Pipeline/docs/IMAGE_PIPELINE_ARCHITECTURE_PLAN.md).

---

## 1. System Overview

During flight, three Raspberry Pi Zero 2W compute nodes record synchronized raw frames into their local MicroSD cards:
- **`Nadir`** (Channel 1 / U3)
- **`ObliqueRt`** (Channel 0 / U2)
- **`ObliqueFwd`** (Channel 2 / U4)

Each capture produces a `.byr` file containing:
- 4 KB binary header (timestamps, trigger sequence counters, hardware ID, camera orientation, exposure time, analog gain, digital gain).
- Full 4056×3040 RAW12 pixels, either RAW or losslessly compressed as identified
  by that file's header. Compression-enabled capture may fall back to RAW.

---

## 2. Environment Setup

Install Python package requirements on your workstation:
```bash
pip install -r image_pipeline/requirements.txt
```

Verify that the C-acceleration library `image_pipeline/lib/libdpcm.so` is present.

---

## 3. Offloading Cards via Triad De-Enrollment (`de_enroll_triad.py`)

When returning from a flight day with three cards pulled from the airframe:

### Interactive 3-Card Wizard:
Run the wizard and specify your destination project directory:
```bash
python3 image_pipeline/tools/de_enroll_triad.py --wizard --dest /path/to/project_surveys
```

#### Workflow Steps:
1. Insert **Card 1**. Inventory every mission/sortie/role contribution, using full
   header identity. A dataset folder such as `261107_1200_c7b8e1a0/` displays an
   abbreviated UUID; the manifest retains the full identity and card CID.
2. Prompt asks to safely unmount. Remove Card 1.
3. Insert **Card 2**. Automatically detected as `Nadir`. Files copied and verified.
4. Insert **Card 3**. Automatically detected as `ObliqueFwd`. Files copied and verified.
5. The manifest distinguishes all three roles offloaded from a complete set of
   triads. Missing capture indices remain gaps. Reinserted/no-new-data cards do
   not advance the channel count; interrupted copies can resume after verification.

The target receipt workflow verifies hashes/readback, commits host evidence
before card markers and blocks normal wiping of unreadable/unverified media.
Keep verified originals immutable; processing/PPK uses working copies.

### Single-Card / Scripted Ingest:
If copying a single mounted partition manually:
```bash
python3 image_pipeline/tools/de_enroll_triad.py \
  --source /media/$USER/imagery \
  --dest /path/to/project_surveys \
  --unmount
```

---

## 4. Converting Raw Imagery (`byr_pipeline.py`)

Once a sortie folder is populated with `.byr` files, run the master conversion pipeline:

```bash
python3 image_pipeline/tools/byr_pipeline.py \
  --input /path/to/project_surveys/261107_1200_c7b8e1a0 \
  --output /path/to/deliverables/261107_1200_c7b8e1a0 \
  --auto-ev \
  --workers 8
```

### Outputs Produced:
- **`dng/` Directory:** Standard Adobe DNG v1.4 RAW files with embedded EXIF, GPS coordinates, camera serial numbers, and exposure parameters. Ready for import into Pix4D, Agisoft Metashape, or RealityCapture.
- **`jpg/` Directory:** Processed JPEGs with matching identity/geotags. Both
  products use the agreed symmetric even crop; originals retain full raw size.

Normal conversion requires canonical header v2 and its explicit sortie/validity
fields. It must not replicate missing rows or silently process earlier layouts.

### Useful Pipeline Options:
- `--auto-ev`: Enables automatic midtone centering and dynamic exposure compensation across variable lighting.
- `--workers <N>`: Sets number of parallel worker processes (defaults to 4; recommend setting to match CPU threads).
- `--quality <Q>`: JPEG output quality (1-100, default: 95).
- `--denoise`: Applies wavelet raw denoising for low-light or high-gain flights.
- `--contrast <C>`: Adjusts contrast multiplier (e.g. `1.15` for subtle boost).

---

## 5. End-to-End Batch Ingestion (`tricam_ingest.py`)

To scan multiple raw folders, verify synchronization triplets, and render all outputs in a single command:

```bash
python3 image_pipeline/tools/tricam_ingest.py \
  --inputs /path/to/card1_dump /path/to/card2_dump /path/to/card3_dump \
  --output /path/to/unified_output \
  --quality 95
```
