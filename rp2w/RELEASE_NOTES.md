# RP2W Compute Node Firmware - Release Notes

## Release r51 (Current Production)

- **Release Tag:** `r51`
- **Git Commit:** `d48d2cf`
- **Build Timestamp:** `2026-11-03T23:29:57Z`
- **Target Hardware:** Raspberry Pi Zero 2W (3× Compute Nodes per Airframe)
- **Overlay Package:** `rp2w/releases/r51/x500.apkovl.tar.gz`
- **Overlay SHA-256:** `f0fa063a21bc9fa77c994178cc8e54ee2a764c99e824366a3ad3056f3f97e7c9`

### Summary of Changes
- feat(rp2w): integrate public release repository staging and auto OS download
- feat(rp2w): enroll production release r50 with continuous in-survey AEC and flash exclusivity
- feat(rp2w): implement chronological sortie storage, atomic log relocation, AEC calibration sweep, and release r48
- docs(rp2w): update debug shell spec with GP5/GP6 and internal pullup analysis
- docs(rp2w): add multi-node debug shell subsystem specification v1.0

## Release r50 (Current Production)

- **Release Tag:** `r50`
- **Git Commit:** `f764b56`
- **Build Timestamp:** `2026-11-02T16:09:00Z`
- **Target Hardware:** Raspberry Pi Zero 2W (3× Compute Nodes per Airframe: Nadir, ObliqueRt, ObliqueFwd)
- **Overlay Package:** `rp2w/releases/r50/x500.apkovl.tar.gz`
- **Overlay SHA-256:** `426ee4347781fbc05e3f3242ea86938b81be9b168a3fb7e868a834927cb1bb8f`

---

### Key Operational Capabilities & Changes

#### 1. Continuous In-Survey Auto Exposure Control (AEC)
- Automatically adapts camera exposure across varying terrain reflectance and solar lighting conditions during active survey transects.
- Implements four strict photogrammetric safeguards:
  - **Deadband Tolerance ($\pm 0.25\text{ EV}$):** Prevents hunting and frame-to-frame exposure oscillations over uniform terrain.
  - **Damped Slew Rate ($\le \pm 0.05\text{ EV/frame}$):** Smooth transitions across adjacent frames for consistent photogrammetric bundle adjustment.
  - **Hard Shutter Floor ($1/1000\text{ s}$ control loop, $1/500\text{ s}$ manual minimum):** Eliminates motion blur even under low light.
  - **Highlight Protection:** Weighted metering protects bright surfaces and highlights from sensor clipping.

#### 2. Flash Exclusivity Invariant
- Automatically gates off all non-image disk writes (such as background system logging and diagnostic updates) during active survey transects.
- Guarantees 100% of MicroSD bus write bandwidth is reserved for raw frame capture, preventing frame drops during high-frequency shooting.

#### 3. Chronological Sortie Organization
- Images and diagnostic logs are automatically organized into per-flight sortie directories:
  `/media/imagery/SORTIE_YYYYMMDD_HHMMSS/`
- Sortie logs are atomically relocated from staging memory upon sortie completion.

#### 4. High-Speed 100 MHz SDIO Clocking
- Default production `usercfg.txt` enables `dtparam=sd_overclock=100` for native carrier board MicroSD sockets, maximizing continuous sequential write throughput.

#### 5. Fleet Parity Consensus & Diagnostic Signaling
- Compute nodes transmit monotonic revision `50` over the I2C mailbox to the KB2040 orchestrator at 1.0 Hz.
- If a compute node runs an outdated or divergent firmware revision relative to the airframe baseline, its on-board ACT LED automatically signals a distinct **Triple-Wink** advisory pattern (`400ms Beacon + 3× 80ms Winks`) while retaining flight readiness.

---

### Release Artifacts

| File | Description |
|---|---|
| `x500.apkovl.tar.gz` | Production Alpine Linux rootfs overlay archive |
| `usercfg.txt` | Raspberry Pi firmware boot configuration (100 MHz clocking & overlays) |
| `cmdline.txt` | Kernel command line arguments (silent boot, memory allocation) |
| `release_manifest.json` | Release checksums (SHA-256), git commit hash, and build metadata |

---

### Field Provisioning Quickstart

To provision a blank or recycled MicroSD card:
```bash
sudo ./rp2w/tools/sd-prep.sh /dev/sdX --release latest
```
*(The tool will automatically download and verify the base Alpine Linux OS tarball if not already cached locally).*
