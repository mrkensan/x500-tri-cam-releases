# Image Pipeline Tools - Release Notes

## Release v1.0 (Production Tools)

- **Target Systems:** Host Processing Workstations (Linux x86_64, macOS, Windows)
- **Primary Modules:** Ingestion, Triad De-Enrollment, and Bayer RAW12 Processing
- **Binary Components:** Pre-compiled `libdpcm.so` (Linux x86_64 C accelerator)

---

### Key Operational Capabilities

#### 1. Multi-SD Card Triad De-Enrollment (`de_enroll_triad.py`)
- Purpose-built for the "Bin of Cards" operational model where three MicroSD cards (`Nadir`, `ObliqueRt`, `ObliqueFwd`) are offloaded one by one on the workstation.
- Features:
  - Automatically identifies camera role (`Nadir`, `ObliqueRt`, `ObliqueFwd`) and card CID from `.byr` file headers.
  - Copies and validates raw imagery into a unified, sortie-indexed project folder (`SORTIE_YYYYMMDD_HHMMSS/`).
  - Maintains `triad_manifest.json` tracking ingested cards, total files, and any missing channels.
  - Interactive wizard mode (`--wizard`) guides operators through card swaps with automatic partition detection and safe unmounting.

#### 2. Synchronized Ingestion & Harmonization (`tricam_ingest.py`)
- Traverses multi-node raw directories and groups captures into synchronized triplets by master sequence index (`seq`).
- Detects orphaned frames or timing skew across channels.
- Provides unified one-step pipeline invocation to batch-convert full airframe datasets.

#### 3. Master Bayer RAW12 Pipeline (`byr_pipeline.py`)
- Converts raw `.byr` containers (4 KB hardware metadata header + 18.5 MB packed RAW12) into standard, photogrammetry-ready deliverables:
  - **Adobe DNG RAW v1.4:** Standard 16-bit DNG files with full EXIF, camera geometry, GPS coordinates, shutter speeds, and ISO metadata embedded directly. Compatible with Pix4D, Agisoft Metashape, RealityCapture, and OpenDroneMap.
  - **High-Resolution JPEGs:** Converted with tunable quality, camera or auto white balance, contrast lifting, and optional wavelet denoising.
- Multi-process parallel worker pool scales linearly across all workstation CPU cores.

#### 4. Hardware-Accelerated DPCM Decompression (`libdpcm.so`)
- Bundles a high-speed C shared library (`lib/libdpcm.so`) for Rice-encoded DPCM decompression, eliminating Python runtime overhead during large survey dataset conversions.

---

### Host Setup & Requirements

1. Install Python package dependencies:
   ```bash
   pip install -r image_pipeline/requirements.txt
   ```

2. Verify pipeline execution:
   ```bash
   python3 image_pipeline/tools/de_enroll_triad.py --help
   python3 image_pipeline/tools/byr_pipeline.py --help
   ```
