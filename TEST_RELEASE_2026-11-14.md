# Tri-Cam test release (M6): tester notes

Published 2026-11-14 in the releases repository (`kb2040/releases/r183`, `rp2w/releases/r86`; `latest` points to
them). Released at the user's direction before the full requalification, which runs on our bench in parallel with
testing: what is verified so far is listed under "Verification" below.

## What is in it

| Part | Version | Notes |
|---|---|---|
| KB2040 firmware | r183 (`4ac305d`, `main`; UF2 SHA-256 `b86e3efd88c04d6d...`) | plan interface, settle triggers, Plan Loader installer |
| RP2W node overlay | r86 (`42b0a52`, `main`; overlay SHA-256 `68a1040119108b4e...`) | AEC starts within its limits |
| Plan Loader (flight-controller script) | build 3, CRC `3FE7BAD7`, 32,641 bytes | carried by the KB2040, which installs it itself |
| Plan tools | `kb2040/tools/plan/` | `tricam_plan.py` (validate, stamp, sample), the sample plan and its README, the Plan Loader script |
| Image Pipeline | r2 (unchanged) | reading r86 files not yet re-checked |

The previous releases (KB2040 r85, RP2W r64, Image Pipeline r2) stay in the releases repository as the rollback.

## Installing

1. **Nodes:** from the releases repository, `sudo ./rp2w/tools/sd-prep.sh /dev/sdX --release latest` for each node's
   card (it wipes the card; check the device with `lsblk` first).
2. **KB2040:** flash `kb2040/releases/latest/tri_cam_kb2040.uf2` with `kb2040/tools/flash_kb2040.py`.
3. **Plan Loader:** nothing to do by hand. With the vehicle disarmed and the autopilot connected, the Tri-Cam checks the
   script on the flight controller about 8 s after it hears it, and if it is missing or not the build it carries,
   it writes it (about 8 s), enables scripting if needed and restarts the flight controller once:
   `Tri-Cam: installing Plan Loader build 3`, `Tri-Cam: Plan Loader installed; restarting FC`, then
   `Tri-Cam: Plan Loader build 3 installed`. It never does this while armed.
4. **Flight controller (ArduPilot 4.7):** do not skip the auxiliary-authorization arming check (`ARMING_SKIPCHK` bit
   17): it is how the Plan Loader allows or blocks arming. The script uses at most about 97 KB of the default Lua heap.

## Plans

* Start from `tricam_sample.plan`: every normal Tri-Cam command, narrated, with marked spots for your waypoints (its
  README explains each block). `python3 tricam_plan.py stamp tricam_sample.plan my.plan` gives your plan its own
  mission UUID; `python3 tricam_plan.py validate my.plan` checks it before you upload.
* A plan that uses Tri-Cam commands needs the Tri-Cam header (the first #217 items); never edit those items by hand.
* QGroundControl's Survey camera triggering (`#206`) is refused in a plan: turn it off in the Survey tool.
* After upload the flight controller says `Tri-Cam: Plan 1a2b3c4d Loaded` (your UUID's first eight digits); at arming
  the Tri-Cam says `Tri-Cam: Mission 1a2b3c4d sortie <date_time>`. If the plan has a problem, arming is refused with
  `PreArm: Tri-Cam: PLAN ERROR (...) item N`, the first problem by item number.

## Exposure

* Change exposure, ISO, AEC limits or compression while disarmed or paused (IDLE); a running survey refuses changes
  (`refused (BUSY)`). In a plan: Sensor or Series items between a Pause and the next Start, as in the sample.
* The cameras need two frames to apply a new exposure. The Tri-Cam spends them itself (two discarded triggers) after a
  change and after every arming, and a survey Start waits for them: the first survey frame carries the new setting.
  **A single photo taken within about a second of a change may still show the old setting.**
* Every image's BYR header records the exposure and gain the sensor actually used (from the sensor's own data,
  flagged LIVE), so the files are always the truth.

## Known limits of this release

* **AEC and AEC_Cal** do not yet account for the two-frame delay: they converge, but more slowly than they could (the
  fix is the next milestone). With AEC on, the limits now hold from the first frames.
* **Two armings within the same minute** reuse image file names, and the second sortie's images replace the first's.
  Wait a minute between armings when the images matter.
* **Plan Loader install:** the main cases are covered (missing script, older build, edited file, scripting off, arming
  during an install). If the check fails while the flight controller is still starting, it is retried only after the
  flight controller's next restart.
* **Bench-tested only:** Copter on the bench, no flight yet.

## Verification (at publication)

* Host: KB2040 18 test suites, the reference model and linter (84 tests), Plan Loader 29 Lua tests on two interpreters,
  RP2W 8 test suites.
* Bench, KB2040 r183 candidate code (M5): exposure end to end on ObliqueFwd (the next frame carries the setting on every
  path), the Plan Loader install (main cases), the plan-interface battery up to the second sortie before the run was
  stopped for publication.
* All three nodes on r86 (version check MATCH). ObliqueRt's camera is not detected on our bench (hardware), so the
  triad itself is not yet requalified; that, the RP2W battery and the Image Pipeline check run in parallel.
