# RP2W Compute Node Firmware - Release Notes

> **Historical release descriptions:** entries below retain the behavior/claims
> recorded for each artifact and are not the current design authority. Guide
> §6.2.5 defines the intended one-wink firmware advisory and in-flight darkness.
> Current lifecycle/signaling guidance is in `../docs/kb2040_flashing_guide.md`.
> Documentation reconciliation does not update or recertify these binaries.

## Release r99 (Test release update, 2026-11-16)

- **Release Tag:** `r99`
- **Git Commit:** `bbcb515` (`main`, clean tree)
- **Build Timestamp:** `2026-11-16T07:48:11Z`
- **Overlay:** `rp2w/releases/r99/x500.apkovl.tar.gz` (with `usercfg.txt`: `dtoverlay=imx477`, `sd_overclock=100`,
  and new `gpio=25=op,dh`)
- **Overlay SHA-256:** `610f30ac465dec34a94e41fd38f3f04856897d69bf2cdb2561ce8abd12efcabe`
- **Works with:** KB2040 r201 **only** (required); Image Pipeline r4
- **Tester notes:** [`../TEST_RELEASE_2026-11-14.md`](../TEST_RELEASE_2026-11-14.md)

### Summary of Changes
- **Steady SD write speed (the "critically slow" boots):** a card re-prepared through a USB reader, or with deleted
  files, keeps that space allocated inside the card, which then reclaims it while writing (slow periods, stalls). Each
  boot now trims the card's free space before the startup write test (about 2 s; a few seconds the first time). On the
  bench the worst card went from 7 of 24 boots below 15 MB/s to 29.5-30.3 MB/s on every boot. Files are never touched.
- **Boot state on the INT line (KB2040 design D56):** the firmware raises the node's INT line about 1 s after power-on;
  the capture daemon announces itself when ready. Requires KB2040 r201.
- **The camera after a warm restart (changes made, not yet validated):** the camera is powered down before every reboot
  or poweroff, the boot retry leaves it unpowered 2 s, and the camera driver resets a sensor that answers with a stale
  id (model `0x0378`). On the bench the camera came back after four restarts, but the stale state did not occur in
  them, so the fix itself has not yet been seen working. If a node reports its camera missing after a restart, a
  Shutdown then Wake, or a power cycle, recovers it.
- **SD diagnostics:** the startup test records its write profile, the SD clock and error counters in `session.log`; a
  below-nominal result is forwarded to the KB2040 console.
- Otherwise r93 (camera powered down before every halt).

## Release r93 (Test release update, 2026-11-15)

- **Release Tag:** `r93`
- **Git Commit:** `88750e4` (`main`, clean tree)
- **Build Timestamp:** `2026-11-15T09:42:25Z`
- **Overlay:** `rp2w/releases/r93/x500.apkovl.tar.gz` (with `usercfg.txt`: `dtoverlay=imx477`, no longer `always-on`)
- **Overlay SHA-256:** `cd3010f66871dbc0f4bf81576723a7104edba5e3381052da753351605ea64332`
- **Works with:** KB2040 r191 (required for the shutdown order); Image Pipeline r4
- **Tester notes:** [`../TEST_RELEASE_2026-11-14.md`](../TEST_RELEASE_2026-11-14.md)

### Summary of Changes
- **The camera is powered down before every halt** (Power Enable, CAM_GPIO1, goes low): a payload that is shut down no
  longer keeps its three cameras powered, and every boot starts the camera from a power-on reset. The camera regulator
  is no longer `always-on`; the driver holds it while running.
- Everything in r91 (full SD write speed, no fake frames, the sensor reset before its driver loads, kept as a fallback).

## Release r91 (Test release update, 2026-11-15)

- **Release Tag:** `r91`
- **Git Commit:** `d2b1899` (`main`, clean tree)
- **Build Timestamp:** `2026-11-15T09:05:32Z`
- **Overlay:** `rp2w/releases/r91/x500.apkovl.tar.gz`
- **Overlay SHA-256:** `16295e8094d51e5cb09f4c38426691dee0f112d06e90a54a8ff375bd8f3a8661`
- **Works with:** KB2040 r183 (unchanged); Image Pipeline r4
- **Tester notes:** [`../TEST_RELEASE_2026-11-14.md`](../TEST_RELEASE_2026-11-14.md)

### Summary of Changes
- **SD write speed:** a supervisor thread spun at real-time priority (it retried a GPIO line held by the shutdown
  daemon without waiting), stalling SD writes for about 1 s every 2 s: about half speed much of the time, in capture
  too. Fixed (`3951eb5`). Bench, daemon running: 8 of 8 write tests at 20.1-20.5 MB/s (before: 7 of 11 at about 10.6).
- **No fake frames:** a node whose camera was not found fell back to a test generator and wrote synthetic frames to
  its card without end (2.2 GB in two minutes on the bench). It now writes nothing and reports the camera fault
  (`637b222`).
- **Camera after a Pi-only restart:** a camera that stayed powered while only the Pi restarted (a crash, a watchdog
  reboot) was rejected by its driver (model 0x0378 instead of 0x0477) and reported missing. The sensor now gets a
  software reset before its driver loads (`d2b1899`). Bench: recovered and 15 of 15 photos written.

## Release r86 (Test release, 2026-11-14)

- **Release Tag:** `r86`
- **Git Commit:** `42b0a52` (`main`, clean tree)
- **Build Timestamp:** `2026-11-14T22:17:35Z`
- **Overlay:** `rp2w/releases/r86/x500.apkovl.tar.gz`
- **Overlay SHA-256:** `68a1040119108b4e34cfdd4d6757c564f7a3e4d20afcc3d268fcd7c81f882e96`
- **Tester notes:** [`../TEST_RELEASE_2026-11-14.md`](../TEST_RELEASE_2026-11-14.md)

### Summary of Changes
- AEC starts within its limits (the current exposure and ISO are clamped when AEC is turned on or its limits change)
- Works with KB2040 r183 (the plan interface); every image's BYR header records the exposure and gain the sensor used
- Tools (2026-11-15): `rp2w/tools/sd-prep.sh` no longer exits silently on hosts whose root is btrfs (Fedora's
  default: `findmnt --nofsroot`); any failure now prints the line where it stopped; prompts are visible. The overlay is
  unchanged.

## Release r64 (Previous production; rollback)

- **Release Tag:** `r64`
- **Git Commit:** `429c407`
- **Build Timestamp:** `2026-11-06T22:58:37Z`
- **Target Hardware:** Raspberry Pi Zero 2W (3× Compute Nodes per Airframe)
- **Overlay Package:** `rp2w/releases/r64/x500.apkovl.tar.gz`
- **Overlay SHA-256:** `0dbcd4d568122188386c1e04aab81a69c4d253cfb7a9c56fcd278abfdbd9afaf`

### Summary of Changes
- fix(tests): repair the MAVLink regression battery for the sortie folder layout, delayed log flush and rig tooling
- fix(tools): node console discovery by USB identity; never fall back to the FTDI or KB2040 ports
- fix(tests): remove stray leftover lines that made test_serial_metadata.py a SyntaxError
- docs: add the IMX477-AACK-C datasheet digest (rev 0.2.0) referenced by the specs and the sensor guide
- docs: IMX477 sensor behaviour guide, session 8 findings and updated specs

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
