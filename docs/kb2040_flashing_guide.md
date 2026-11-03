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

Upon booting, the on-board NeoPixel (WS2812) LED signals operational status:

| LED Color & Pattern | System State | Meaning |
|---|---|---|
| **Calm Green Breathing** | Standby / Nominal | Autopilot MAVLink connected, all online compute nodes match fleet baseline version (`PARITY_OK`). |
| **Steady Blue** | Armed for Survey | Airframe armed or survey transect active; ready to receive shutter trigger events. |
| **White Flash (Single pulse)** | Camera Trigger | Trigger signal successfully dispatched to all 3 camera nodes. |
| **Yellow / Amber Blink** | Version Divergence | One or more connected compute nodes are running divergent or older firmware versions. (Advisory only; flight is still permitted). |
| **Fast Red Strobe** | Hardware Fault | A critical fault is detected (e.g. camera missing or 1-bit bus degradation). |
