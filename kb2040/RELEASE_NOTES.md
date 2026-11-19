# KB2040 Orchestrator Firmware - Release Notes

## Release r280 (Milepost, 2026-11-19: bench only, **not for the field**; `latest` stays r201)

- **Release Tag:** `r280`
- **Git Commit:** `36d5266` (`main`, clean tree)
- **Build Timestamp:** `2026-11-19T09:00:43Z`
- **Target Hardware:** Adafruit KB2040 (Raspberry Pi RP2040 Dual ARM Cortex-M0+)
- **Firmware Binary:** `kb2040/releases/r280/tri_cam_kb2040.uf2`
- **Binary SHA-256:** `ac9b1358945aa6443a7327f54b19f2f8f6126e3285165ebbd311ab067b551eb1`
- **Carries:** Plan Loader build 5 (installed on the flight controller by the Tri-Cam itself, one FC restart)
- **Works with:** RP2W r125 **only**
- **Status:** a development milepost recorded before mailbox v2. Test pilots keep KB2040 r201 + RP2W r99.

### Summary of Changes (since r201)
- **The post-flight lifecycle (design D57):** a disarm after a flight halts the nodes in order (the pause, PREPARE:
  each node unmounts its imagery, then SHDN); the unit is retired until a plan upload restarts it (`TC_RESTART`, Plan
  Loader build 5) or a power cycle; LED patterns for the halt and its outcome; a lost FC link while armed is treated
  as a crash; restarts follow a persistent record.
- **The halt waits for every node seen operating since arming (issue B, B2):** a node that misses a grant or restarts
  is still waited for, gets PREPARE at its announce, and is named if it never reports READY (`Halt unconfirmed`).
- **The mailbox slave's handler runs from RAM (D58):** fixes the nodes' intermittent I2C read failures and refused
  grants (MB1: none in 15 min under a console flood).
- Plan Loader build 5: the retired gate text, the End rule (`PLAN ERROR (NO_END)`).
- Bench on exactly this build with RP2W r125 (`reports/bench-d57-s6-20261118/README.md` in the KB2040 repository):
  the post-flight run 264/264, plan interface 115/115, end to end 34/34, arming gate 24/24, exposure 47/47, MB1 15/15.

## Release r201 (Test release update, 2026-11-16)

- **Release Tag:** `r201`
- **Git Commit:** `01aef2d` (`main`, clean tree)
- **Build Timestamp:** `2026-11-16T09:49:57Z`
- **Target Hardware:** Adafruit KB2040 (Raspberry Pi RP2040 Dual ARM Cortex-M0+)
- **Firmware Binary:** `kb2040/releases/r201/tri_cam_kb2040.uf2`
- **Binary SHA-256:** `689d7d59935b63dde8d367bf11da7e7d20f644ccb09a14fa5f810628bb86bb80`
- **Carries:** Plan Loader build 4 (unchanged)
- **Works with:** RP2W r99 **only** (required: with older node cards every node shows "no boot")
- **Tester notes:** [`../TEST_RELEASE_2026-11-14.md`](../TEST_RELEASE_2026-11-14.md)

### Summary of Changes
- **Each node's boot state from its INT line (design D56):** the KB2040 sees, per node and within seconds, whether a
  node is not booting at all (`Tri-Cam: <role> no boot (SD card?)`, 3 s after power-on or Wake), booting (firmware up
  about 1 s after power-on), or ready (the node announces itself, about 20-25 s). The mailbox polls only nodes that
  have announced themselves; a node that restarts is caught at its next poll (`Tri-Cam: <role> restarted`) and comes
  back by itself. No more misreading a slow boot as "halted" (which silenced the bus and blocked arming).
- The INT lines are open-drain with the chips' internal pulls only: no hardware change (R11-R13 stay unfitted).
- Otherwise r192 (arming blocked while a camera channel is not ready, D55; camera power sequencing, D54).
- Bench: 20 Shutdown -> Wake cycles with all three nodes; a KB2040 restart under running nodes; a node restart; a node
  without a card; the D55 arming test 20 of 20 on exactly this build.

## Release r192 (Test release update, 2026-11-15)

- **Release Tag:** `r192`
- **Git Commit:** `43c6e92` (`main`, clean tree)
- **Build Timestamp:** `2026-11-15T10:59:51Z`
- **Target Hardware:** Adafruit KB2040 (Raspberry Pi RP2040 Dual ARM Cortex-M0+)
- **Firmware Binary:** `kb2040/releases/r192/tri_cam_kb2040.uf2`
- **Binary SHA-256:** `acfc03b7990d02188235b4d667c2558c7e2d1e6740490346bd0a1b47c91b8784`
- **Carries:** Plan Loader build 4 (installed on the flight controller by the Tri-Cam itself, one FC restart)
- **Works with:** RP2W r93 (unchanged)
- **Tester notes:** [`../TEST_RELEASE_2026-11-14.md`](../TEST_RELEASE_2026-11-14.md)

### Summary of Changes
- **Arming is blocked while any camera channel is not ready (design D55):** its node does not answer (no SD card,
  halted, offline), its camera is missing, or its card is unusable (SD error or critically slow, 1-bit bus,
  filesystem error). Free flight and plan flights alike: `PreArm: Tri-Cam: not ready: <channels>`. The Tri-Cam
  says why every 8 s (`Tri-Cam: blocked: OblqRt off,Nadir cam,OblqFw SD`).
- **Deliberate override for one arming:** `TC_ARM_OVERRIDE` (31033, p1 = 6283) from the ground station;
  `kb2040/tools/plan/TriCamActions.json` makes it a QGroundControl Fly View action. The arming is audited.
- **No SD cards is no longer reported as a safe shutdown:** `Tri-Cam: no camera node running (SD cards?)`.
- Otherwise r191 (camera power sequencing, D54).

## Release r191 (Test release update, 2026-11-15)

- **Release Tag:** `r191`
- **Git Commit:** `a13d8a7` (`main`, clean tree)
- **Build Timestamp:** `2026-11-15T10:02:58Z`
- **Target Hardware:** Adafruit KB2040 (Raspberry Pi RP2040 Dual ARM Cortex-M0+)
- **Firmware Binary:** `kb2040/releases/r191/tri_cam_kb2040.uf2`
- **Binary SHA-256:** `eb011df0ab5a959ba2b7263319c4ee210dc9801d96fa52f113a9bd5103f24c01`
- **Works with:** RP2W r93 (required: the nodes power their cameras down at shutdown); Plan Loader build 3 (unchanged)
- **Tester notes:** [`../TEST_RELEASE_2026-11-14.md`](../TEST_RELEASE_2026-11-14.md)

### Summary of Changes
- **The trigger line follows camera power (design D54):** at Wake the camera trigger line is driven only once the
  nodes run and a camera reports up (no longer at once); at Shutdown the streams are stopped first, then the line is
  released, then the nodes are told to halt (and power their cameras down, RP2W r93).
- Otherwise r183's plan interface, settle triggers and Plan Loader installer, unchanged.

> **Historical release descriptions:** entries below are not the current
> operational authority. Use User Guide Table 2 and
> `../docs/kb2040_flashing_guide.md`: cyan is operational, solid blue is confirmed
> safe Pi halt, and white means trigger issued. Older color/command claims are
> not adopted by the documentation review. No binary was changed or recertified.

## Release r183 (Test release, 2026-11-14)

- **Release Tag:** `r183`
- **Git Commit:** `4ac305d` (`main`)
- **Build Timestamp:** `2026-11-14T22:18:38Z`
- **Target Hardware:** Adafruit KB2040 (Raspberry Pi RP2040 Dual ARM Cortex-M0+)
- **Firmware Binary:** `kb2040/releases/r183/tri_cam_kb2040.uf2`
- **Binary SHA-256:** `b86e3efd88c04d6d55188ef734908c121324889faa69b25cffdf3ac2c80e354c`
- **Plan Loader carried:** build 3, CRC `0x3fe7bad7`, 32,641 bytes (installed on the flight controller by the Tri-Cam)
- **Tester notes:** [`../TEST_RELEASE_2026-11-14.md`](../TEST_RELEASE_2026-11-14.md)

### Summary of Changes
- Plan interface: the Tri-Cam plan header (#217), its state machine and commands; plans are checked and staged by the
  Plan Loader on the flight controller, which allows or blocks arming
- The Tri-Cam installs and updates the Plan Loader itself (MAVFTP; enables scripting, restarts the flight controller)
- Exposure: two settle triggers after a change and after arming, so the next survey frame carries the new setting
- Fix: a single photo arriving just after a pad check was accepted but never taken
- Plan tools in `kb2040/tools/plan/`: the narrated sample plan, `tricam_plan.py stamp` and `validate`

## Release r85 (Previous production; rollback)

- **Release Tag:** `r85`
- **Git Commit:** `4b23ef5`
- **Build Timestamp:** `2026-11-06T22:59:44Z`
- **Target Hardware:** Adafruit KB2040 (Raspberry Pi RP2040 Dual ARM Cortex-M0+)
- **Firmware Binary:** `kb2040/releases/r85/tri_cam_kb2040.uf2`
- **Binary SHA-256:** `62c1e006452a187be3136f05a4c1fb9afd105d24aefe67fe00f975cb9f8fe137`

### Summary of Changes
- docs: trigger polarity and timing contract, STREAM_ENABLE mailbox flag, trigger lab commands
- feat(trigger): idle-high active-low XVS trigger, trigger lab, STREAM_ENABLE flag and stream-restart poke
- feat(tools): implement sustained cadence stress testing harness with HTML reporting
- docs(test): author SYSTEM_TESTING_AND_VALIDATION_SPEC.md and update checkpoints
- feat(flight_plans): implement flight-plan library and automated test assertion engine

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
