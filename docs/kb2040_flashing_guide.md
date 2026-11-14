# KB2040 Orchestrator Flashing Guide

This guide describes how to update the firmware on the **Adafruit KB2040** orchestrator module responsible for hardware shutter synchronization, MAVLink telemetry, and fleet version consensus.

---

## 1. Overview & Firmware Artifact

- **Target Architecture:** Raspberry Pi RP2040 (Dual ARM Cortex-M0+ @ 125 MHz)
- **Current Production Binary:** `kb2040/releases/latest/tri_cam_kb2040.uf2`
- **Firmware Format:** UF2 (USB Flashing Format)

---

## 2. Flashing Procedure (1200-Baud Updater)

The primary and standard method for flashing the KB2040 is using the automated **1200-baud updater script** (`flash_kb2040.py`). 

This utility connects to the KB2040's active USB CDC serial interface and issues a standard 1200-baud "touch reset". This causes the RP2040 firmware to immediately reboot into its internal ROM bootloader without requiring any physical buttons to be pressed or holding down the boot switch. The script then detects the resulting `RPI-RP2` mass-storage drive, mounts it, deploys the UF2 binary, and reboots the board into operation.

### Prerequisites
Ensure `pyserial` is installed on your workstation:
```bash
pip install pyserial
```

### Execution
Connect the KB2040 to your workstation via USB and run:
```bash
sudo python3 ./kb2040/tools/flash_kb2040.py
```

### Output Walkthrough
```text
[FLASH] Triggering 1200-baud reset on /dev/serial/by-id/usb-Raspberry_Pi_Pico_...
[FLASH] Waiting for RPI-RP2 bootloader drive...
[FLASH] Bootloader detected at /dev/disk/by-label/RPI-RP2
[FLASH] Copying /path/to/kb2040/releases/latest/tri_cam_kb2040.uf2 to /mnt/pico/...
[FLASH] Firmware copied! Board is flashing and rebooting...
[FLASH] SUCCESS! KB2040 is running the new firmware.
```

### Flashing a Specific Release
By default, the updater script flashes the current production release (`kb2040/releases/latest/tri_cam_kb2040.uf2`). To flash a specific binary or release version, pass the path directly:
```bash
sudo python3 ./kb2040/tools/flash_kb2040.py kb2040/releases/r78/tri_cam_kb2040.uf2
```

---

## 3. Post-Flash Status Indication

The intended operating vocabulary follows User Guide Table 2. The sole detailed
owner is the [airframe signaling spec](../../Tri-Cam%20Module/KB2040/docs/LED_AND_ALERT_SUBSYSTEM_SPEC.md).
A successful flash or a particular release number alone does not verify every
lifecycle behavior; check the release's validation scope before field use.

| LED Color & Pattern | System State | Meaning |
|---|---|---|
| **Cyan breathing (2 s)** | Boot / acquisition | Awaiting GNSS time and camera-node discovery. |
| **Green breathing (2 s)** | Ground ready | Preflight checks nominal; periodic pad checks use a 2-second cadence. |
| **Amber flashing (2.5 Hz)** | Ground caution | Lens cap, degraded usable storage rate, or low remaining capacity. |
| **Red flashing (2.5 Hz)** | Ground critical | Missing/unusable camera or storage; deliberate PIC override policy applies. |
| **Solid green / amber / red** | Ground armed | Nominal / accepted caution / critical override respectively. |
| **Solid cyan** | Flight-ready / capture base state | Operational; not safe to remove power. |
| **White flash (150 ms)** | Retained trigger issued | Confirms the orchestrator trigger, not that all three images reached storage. |
| **Blue strobe (4 Hz)** | In-flight/ground recovery or finalization | Draining images, then logs/sync; ground state 9 also completes halt. Wait. |
| **Solid blue** | Confirmed safe Pi halt | Stable ground, disarmed, final cleanup and halt complete. Safe to remove power/cards. |

Node ACT LEDs follow Guide §6.2.5: one wink for firmware divergence, two for
storage caution, three for lens cap. They are dark while airborne; armed-on-ground is distinct.
Storage classification thresholds remain under design review.
