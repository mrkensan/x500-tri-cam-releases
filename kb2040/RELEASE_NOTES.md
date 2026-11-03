# KB2040 Orchestrator Firmware - Release Notes

## Release r80 (Current Production)

- **Release Tag:** `r80`
- **Git Commit:** `e11d211`
- **Build Timestamp:** `2026-11-03T23:30:15Z`
- **Target Hardware:** Adafruit KB2040 (Raspberry Pi RP2040 Dual ARM Cortex-M0+)
- **Firmware Binary:** `kb2040/releases/r80/tri_cam_kb2040.uf2`
- **Binary SHA-256:** `566e6e14eb15d3e0aa2d73d2c20b7929d7944ad837778d1b0ccb263c4bfe2413`

### Summary of Changes
- fix(tools): support dual resolution for default UF2 in flash_kb2040.py
- feat(kb2040): integrate git revision tracking and release enrollment pipeline
- feat(mavlink): implement DIGICAM_CONFIGURE (#202), in-survey AEC, and preflight calibration handoff
- feat(mavlink): unify command dictionary, chronological sortie identity, and calibration sweep mode
- docs(kb2040): update debug shell spec with GP5/GP6 and internal pullup analysis

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

Connect the KB2040 module via USB to your workstation and run the 1200-baud updater script:
```bash
sudo python3 ./kb2040/tools/flash_kb2040.py
```

The updater script automatically:
1. Detects the KB2040 USB serial device.
2. Triggers a 1200-baud touch reset to switch the RP2040 microcontroller into its ROM bootloader without pressing physical buttons.
3. Mounts the resulting `RPI-RP2` volume at `/mnt/pico`.
4. Copies `kb2040/releases/latest/tri_cam_kb2040.uf2`.
5. Reboots the board into the active production firmware.
