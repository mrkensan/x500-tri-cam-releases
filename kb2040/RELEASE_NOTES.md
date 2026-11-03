# KB2040 Orchestrator Firmware - Release Notes

## Release r78 (Current Production)

- **Release Tag:** `r78`
- **Git Commit:** `9fda0c6`
- **Build Timestamp:** `2026-11-02T16:07:29-08:00`
- **Target Hardware:** Adafruit KB2040 (Raspberry Pi RP2040 Dual ARM Cortex-M0+)
- **Firmware Binary:** `kb2040/releases/r78/tri_cam_kb2040.uf2`
- **Binary SHA-256:** `46d3599ab5957841818938ec6039f9a0846447a20ea43d6acbcf6228aad8665a`

---

### Key Operational Capabilities & Changes

#### 1. Hardware-Synchronized Tri-Camera Triggering
- Dual-core timing architecture on RP2040 provides microsecond-accurate hardware trigger pulses simultaneously to all three Raspberry Pi Zero 2W nodes (`Nadir`, `ObliqueRt`, `ObliqueFwd`).
- Generates precise shutter exposure timestamps linked to GNSS PPS timekeeper.

#### 2. Autopilot Integration via MAVLink v2
- Full telemetry integration with ArduPilot and PX4 flight controllers over UART:
  - Command `#203` (`MAV_CMD_DO_DIGICAM_CONTROL`): Mission-driven shutter triggering.
  - Command `#202` (`MAV_CMD_DO_DIGICAM_CONFIGURE`): Dynamic exposure control mode shifts (Preflight calibration sweep vs. In-survey AEC vs. Fixed manual).
  - Emits `CAMERA_FEEDBACK` and camera status packets to Ground Control Station (QGroundControl / Mission Planner).

#### 3. Airframe Fleet Parity Consensus Engine
- Polls all three compute nodes at 1.0 Hz over I2C mailbox (`0x80`).
- Evaluates majority consensus on firmware revisions across nodes:
  - Identifies baseline version and detects any divergent outlier channel.
  - Downlinks advisory flags to outlier nodes to qualify ACT LED visual signaling.
  - Reports objective version status and revision deltas over the debug console.

#### 4. Preflight Calibration Sweep & Transect Coordination
- Orchestrates multi-step exposure calibration sweep prior to survey start to establish ground-truth photogrammetric baseline.
- Commands seamless handoff into continuous AEC upon survey entry.

#### 5. Airframe Status LED Indication (WS2812/NeoPixel)
- Single-wire high-visibility airframe LED provides real-time operational state indication:
  - Calm Green Breathing: Standby / Parity OK.
  - Steady Blue: Survey Armed / Ready for Triggers.
  - Bright White Flash: Exposure Trigger Event.
  - Yellow / Amber Patterns: Firmware Divergence Advisory.
  - Red Blink: Critical Hardware Fault (Camera disconnected or SD bus fault).

---

### Release Artifacts

| File | Description |
|---|---|
| `tri_cam_kb2040.uf2` | Pre-compiled RP2040 UF2 firmware binary |
| `release_manifest.json` | Release checksums (SHA-256), git commit hash, and build metadata |

---

### Flashing Quickstart

#### Method A: Automated Flashing Script (Recommended)
Connect the KB2040 via USB to your workstation:
```bash
sudo python3 ./kb2040/tools/flash_kb2040.py
```
*(The script will issue a 1200-baud reset, mount the bootloader volume, and copy the latest UF2).*

#### Method B: Manual BOOTSEL Drag-and-Drop
1. Hold down the tiny **BOOT** button on the KB2040 while plugging in the USB cable.
2. The board will mount as a mass-storage drive named `RPI-RP2`.
3. Copy `kb2040/releases/latest/tri_cam_kb2040.uf2` to the `RPI-RP2` drive.
4. The board will automatically flash, dismount, and boot the new firmware.
