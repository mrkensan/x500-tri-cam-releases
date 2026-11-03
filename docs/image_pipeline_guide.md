# Image Pipeline Processing Guide

This guide describes how to use the host-side Image Pipeline utilities to offload, organize, and convert raw `.byr` photogrammetry datasets captured by the GCC X500 Tri-Cam system.

---

## 1. System Overview

During flight, three Raspberry Pi Zero 2W compute nodes record synchronized raw frames into their local MicroSD cards:
- **`Nadir`** (Channel 0 / U3)
- **`ObliqueRt`** (Channel 1 / U2)
- **`ObliqueFwd`** (Channel 2 / U4)

Each capture produces a `.byr` file containing:
- 4 KB binary header (timestamps, trigger sequence counters, hardware ID, camera orientation, exposure time, analog gain, digital gain).
- 18.5 MB packed 12-bit raw Bayer pixel stream (Sony IMX477, 4056×3040 resolution).

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
1. Insert **Card 1**. The script detects the mounted card, reads the `.byr` header to determine its role (e.g. `ObliqueRt`), copies files into `/path/to/project_surveys/SORTIE_YYYYMMDD_HHMMSS/`, and records the card's CID.
2. Prompt asks to safely unmount. Remove Card 1.
3. Insert **Card 2**. Automatically detected as `Nadir`. Files copied and verified.
4. Insert **Card 3**. Automatically detected as `ObliqueFwd`. Files copied and verified.
5. The script generates `triad_manifest.json` confirming that all three channels are complete with matching sequence numbers.

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
  --input /path/to/project_surveys/SORTIE_YYYYMMDD_HHMMSS \
  --output /path/to/deliverables/SORTIE_YYYYMMDD_HHMMSS \
  --auto-ev \
  --workers 8
```

### Outputs Produced:
- **`dng/` Directory:** Standard Adobe DNG v1.4 RAW files with embedded EXIF, GPS coordinates, camera serial numbers, and exposure parameters. Ready for import into Pix4D, Agisoft Metashape, or RealityCapture.
- **`jpg/` Directory:** High-resolution processed JPEGs with identical geotags and metadata.

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
