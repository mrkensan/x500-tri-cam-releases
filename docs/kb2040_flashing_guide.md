# KB2040 Orchestrator Flashing Guide

This guide describes how to update the firmware on the **Adafruit KB2040** orchestrator module responsible for hardware shutter synchronization, MAVLink telemetry, and fleet version consensus.

---

## 1. Overview & Firmware Artifact

- **Target Architecture:** Raspberry Pi RP2040 (Dual ARM Cortex-M0+ @ 125 MHz)
- **Current Production Binary:** `kb2040/releases/latest/tri_cam_kb2040.uf2`
- **Firmware Format:** UF2 (USB Flashing Format)

---

## 2. Flashing Procedures

### Method 1: Automated Python Script (Recommended)

When the KB2040 is connected via USB and running active firmware, the Python utility automatically commands a 1200-baud reset into the RP2040 ROM bootloader, mounts the drive, and copies the UF2 binary.

#### Prerequisites:
Install `pyserial` if not already installed:
```bash
pip install pyserial
```

#### Run Flashing Utility:
```bash
sudo python3 ./kb2040/tools/flash_kb2040.py
```

#### Output:
```text
[FLASH] Triggering 1200-baud reset on /dev/serial/by-id/...
[FLASH] Waiting for RPI-RP2 bootloader drive...
[FLASH] Bootloader detected at /dev/disk/by-label/RPI-RP2
[FLASH] Copying .../tri_cam_kb2040.uf2 to /mnt/pico/...
[FLASH] Firmware copied! Board is flashing and rebooting...
[FLASH] SUCCESS! KB2040 is running the new firmware.
```

---

### Method 2: Manual Hardware BOOTSEL Mode

If the board is unresponsive, blank, or has fresh factory firmware:

1. **Locate the Buttons:**
   - On the Adafruit KB2040 board, find the small push button labeled **BOOT** (next to the USB-C connector).
2. **Engage Bootloader:**
   - Press and **hold** the **BOOT** button.
   - While holding **BOOT**, plug the USB-C cable into your workstation.
   - Release the button after 1 second.
3. **Copy Firmware:**
   - The board will enumerate as a USB mass-storage drive named `RPI-RP2`.
   - Copy the UF2 binary to the volume:
     ```bash
     cp kb2040/releases/latest/tri_cam_kb2040.uf2 /media/$USER/RPI-RP2/
     ```
     *(Or drag-and-drop the file using your file manager).*
4. **Reboot:**
   - The RP2040 will immediately flash its internal flash memory, dismount the USB drive, and boot into operation.

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
