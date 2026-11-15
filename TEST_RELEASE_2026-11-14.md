# Tri-Cam test release (M6): tester notes

Published 2026-11-14 in the releases repository (`kb2040/releases/r183`, `rp2w/releases/r86`; `latest` points to
them). Released at the user's direction before the full requalification, which runs on our bench in parallel with
testing: what is verified so far is listed under "Verification" below.

## What is in it

| Part | Version | Notes |
|---|---|---|
| KB2040 firmware | r192 (`43c6e92`, `main`; UF2 SHA-256 `acfc03b7990d0218...`), 2026-11-15 | r183's plan interface, settle triggers and Plan Loader installer; the trigger line follows camera power; arming blocked while a camera channel is not ready |
| RP2W node overlay | r93 (`88750e4`, `main`; overlay SHA-256 `cd3010f66871dbc0...`), 2026-11-15 | r86's changes plus the fixes below |
| Plan Loader (flight-controller script) | build 4, CRC `1C881D6B`, 33,891 bytes | carried by the KB2040, which installs it itself (one FC restart) |
| Plan tools | `kb2040/tools/plan/` | `tricam_plan.py` (validate, stamp, sample), the sample plan and its README, the Plan Loader script |
| Image Pipeline | r4 (2026-11-15) | reads r86 image files (below) |

The previous releases (KB2040 r191, r183 and r85, RP2W r91, r86 and r64, Image Pipeline r2) stay in the releases repository as the rollback. KB2040 r191 or later and RP2W r93 go together.

## Installing

**Update 2026-11-15 (latest): KB2040 r192. Arming is now blocked while a camera is not ready.** `git pull` and flash
the KB2040 (`kb2040/releases/latest/tri_cam_kb2040.uf2`); the nodes stay on r93. With the autopilot connected and
disarmed, the Tri-Cam installs Plan Loader build 4 on the flight controller by itself and restarts it once.

* **What blocks arming:** any camera channel without a running node (no SD card, halted, offline), without its camera,
  or with an unusable card (SD error or critically slow, 1-bit bus, filesystem error). QGC shows
  `PreArm: Tri-Cam: not ready: OblqRt ...`; the Tri-Cam says why every 8 s: `Tri-Cam: blocked: OblqRt off,Nadir cam`
  (`off`: no node, e.g. no SD card; `cam`: camera; `SD`: card). Fix it on the ground.
* **To fly anyway (deliberately):** send the arming override, which allows the next arming only and is recorded. In
  QGroundControl: copy `kb2040/tools/plan/TriCamActions.json` to `~/Documents/QGroundControl/MavlinkActions/` (or the
  `MavlinkActions` folder of your QGC save location), select it in Application Settings (Fly View custom actions),
  then Fly View, Action, "Tri-Cam: allow arming without cameras". Details: `kb2040/tools/plan/README.md`.
* **Known:** the node's startup SD test sometimes reads a good card as critically slow after a boot (open item, under
  investigation); that now blocks arming too. Power-cycle and check again, or use the override if you are sure.

**Update 2026-11-15 (later): KB2040 r191 and RP2W r93, together.** `git pull`, re-prepare each node's card
(`sudo ./rp2w/tools/sd-prep.sh /dev/sdX --release latest`) and flash the KB2040
(`kb2040/releases/latest/tri_cam_kb2040.uf2`). After **Shutdown** in QGC the cameras are now really off (the payload
no longer keeps three cameras powered), and after **Wake** they start clean. Use the two releases together.

**Update 2026-11-15: RP2W r91.** `git pull`, then re-prepare each node's card (`sudo ./rp2w/tools/sd-prep.sh /dev/sdX
--release latest`; it wipes the card, so offload the images first). The KB2040 stays on r183.

* **SD write speed:** r86 halved the cards' write speed much of the time (a busy loop in the capture daemon). If a
  node reported "Slow SD write speed" or the survey interval was raised for storage, that was likely it.
* **No fake frames:** with r86, a node whose camera was not found wrote synthetic frames to its card until it filled.
  Check such a card for a `000000_0000_mock-ses` folder and delete it (re-preparing the card does).
* **Camera after a Pi-only restart:** a node whose Pi restarted on its own came back reporting its camera missing until
  the next power cycle. r91 resets the sensor at boot.

**Update 2026-11-15:** `rp2w/tools/sd-prep.sh` fixed: on Fedora (btrfs root) it exited without printing anything.
`git pull` the releases repository before preparing cards.

**Update 2026-11-15: Image Pipeline r4 reads this release's image files.** `git pull`, then as before:

    python3 image_pipeline/tools/de_enroll_triad.py --source /path/to/mounted/card --dest /path/to/project
    python3 image_pipeline/tools/byr_pipeline.py --input /path/to/project/<SORTIE_UUID8> --output /path/to/project/<SORTIE_UUID8>

* One dataset per mission and sortie, named like the card's folders (`261114_2319_00112233/`).
* The nodes name the obliques `OblqRt` / `OblqFw`; r4 recognises them (r2 counted those cards as missing).
* Images are cropped by 6 rows at the top and bottom (4056 x 3028): in triggered capture the first rows are
  over-exposed. The EXIF time is the exposure centre; exposure, ISO and black level are the sensor's own values.
* `byr_pipeline.py` refuses a dataset with fewer than three cards offloaded; add `--allow-partial` to process it anyway.
* Indoors, horizontal bands in the images are the lights' flicker under the rolling shutter, not a processing fault.

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
