#!/usr/bin/env python3
"""
Automated firmware flash script for Adafruit KB2040 (RP2040)
Performs 1200-baud touch reset, mounts the RPI-RP2 mass-storage volume,
and copies the UF2 firmware binary.
"""

import os
import sys
import time
import glob
import subprocess

try:
    import serial
except ImportError:
    print("[ERROR] pyserial is required. Install with: pip install pyserial")
    sys.exit(1)

MOUNT_DIR = "/mnt/pico"
LABEL_DEV = "/dev/disk/by-label/RPI-RP2"

def run_cmd(cmd, check=True):
    res = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if check and res.returncode != 0:
        raise RuntimeError(f"Command failed ({cmd}): {res.stderr.strip()}")
    return res.stdout.strip()

KB2040_SERIAL_ID = "DF648C8653"

def find_serial_port():
    ports = [p for p in glob.glob(f"/dev/serial/by-id/*{KB2040_SERIAL_ID}*") if "Gadget" not in p]
    if ports:
        return ports[0]
    # Check for any Raspberry Pi Pico / RP2040 device, strictly excluding the Linux USB Gadget & SparkFun tester
    pico_ports = [
        p for p in glob.glob("/dev/serial/by-id/*Pico*")
        if "Gadget" not in p and "E464CC71435B1F22" not in p
    ]
    if pico_ports:
        return pico_ports[0]
    return None

def trigger_1200_baud_reset(port):
    print(f"[FLASH] Triggering 1200-baud reset on {port}...")
    try:
        run_cmd(f"sudo chmod 666 {port}", check=False)
        s = serial.Serial(port, 1200)
        s.close()
    except Exception as e:
        print(f"[FLASH] Warning during reset trigger: {e}")

def wait_for_bootloader(timeout=6.0):
    print("[FLASH] Waiting for RPI-RP2 bootloader drive...")
    start = time.time()
    while time.time() - start < timeout:
        if os.path.exists(LABEL_DEV):
            return True
        time.sleep(0.2)
    return False

def flash_uf2(uf2_path):
    if not os.path.isfile(uf2_path):
        print(f"[ERROR] UF2 binary not found: {uf2_path}")
        sys.exit(1)

    # 1. Check if already in bootloader
    if not os.path.exists(LABEL_DEV):
        port = find_serial_port()
        if port:
            trigger_1200_baud_reset(port)
        else:
            print("[FLASH] No serial port found. Is KB2040 plugged in?")
        
        if not wait_for_bootloader():
            print("[ERROR] RPI-RP2 bootloader did not appear!")
            print("Tip: You can manually hold the BOOTSEL button while plugging in the USB cable,")
            print(f"     then copy {uf2_path} to the mounted RPI-RP2 drive.")
            sys.exit(1)

    print(f"[FLASH] Bootloader detected at {LABEL_DEV}")

    # 2. Mount drive
    os.makedirs(MOUNT_DIR, exist_ok=True)
    run_cmd(f"sudo mount {LABEL_DEV} {MOUNT_DIR}")

    # 3. Copy UF2
    print(f"[FLASH] Copying {uf2_path} to {MOUNT_DIR}...")
    run_cmd(f"sudo cp \"{uf2_path}\" {MOUNT_DIR}/")
    run_cmd("sync")
    run_cmd(f"sudo umount -l {MOUNT_DIR} 2>/dev/null || true", check=False)

    print("[FLASH] Firmware copied! Board is flashing and rebooting...")
    time.sleep(2.0)

    # 4. Set serial permissions
    run_cmd("sudo chmod 666 /dev/ttyACM* /dev/ttyUSB* 2>/dev/null || true", check=False)
    print("[FLASH] SUCCESS! KB2040 is running the new firmware.")

if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    kb2040_dir = os.path.abspath(os.path.join(script_dir, ".."))
    default_uf2 = os.path.join(kb2040_dir, "releases", "latest", "tri_cam_kb2040.uf2")

    target_uf2 = sys.argv[1] if len(sys.argv) > 1 else default_uf2
    flash_uf2(target_uf2)
