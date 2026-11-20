# Tri-Cam Plan Development Kit

Everything needed to produce QGroundControl plans for an aircraft carrying the Tri-Cam, and to check them against the
rules the aircraft applies before it allows arming. It matches **Plan Loader build 5** (plan interface version 1).

| File | What it is for |
|---|---|
| [`PLAN_DEVELOPMENT_GUIDE.md`](PLAN_DEVELOPMENT_GUIDE.md) | The guide: plan structure, the header and command encoding (bit-exact), what each command does in flight, every rule and how to fix it, a worked example |
| `tricam_plan_check.py` | The validator (Python 3.8 or later, standard library only): `validate` a plan, as text or `--json`; `stamp` a plan with a new mission UUID |
| `vectors/encoder_vectors.json` | Bit-exact vectors to test an encoder with: words, headers, fingerprints, conversions |
| `examples/` | Plans that pass every rule: `tricam_sample.plan` (every command, narrated), `example_survey.plan` (the guide's worked example, with the annotation block), `example_survey_plain.plan` (without it), `minimal_survey.plan` (a header without settings) |
| `test_plans/` | One plan per mistake the rules catch, and a few clean ones; `expected_findings.json` lists what each one reports |

## Checking a plan

    python3 tricam_plan_check.py validate my.plan
    python3 tricam_plan_check.py validate my.plan --json

Exit status 0: no errors (the plan may be flown as far as the Tri-Cam rules go); 1: errors (the aircraft would refuse
to arm); 2: the file cannot be read as a plan.

## Writing a plan generator

Read [`PLAN_DEVELOPMENT_GUIDE.md`](PLAN_DEVELOPMENT_GUIDE.md). In short: encode the header and the words exactly as
the guide says, test the encoder against `vectors/encoder_vectors.json`, and validate every plan the generator
produces; the guide's section 9 has the workflow and a checklist.

## Making a plan by hand from the sample

`examples/tricam_sample.plan` has every normal Tri-Cam command, narrated item by item (`_comment` keys), and example
waypoints at the spots where you put your own:

1. **Tri-Cam header** (the first `#217` items): the mission UUID, the survey settings (1.5 s requested, adaptive,
   lossless DPCM compression) and the starting exposure (1/1000 s, ISO 400, all cameras). Never edit these items by
   hand: their check values would no longer match and the aircraft refuses to arm (`PLAN INVALID`).
2. **Take-off.**
3. **AEC_Cal** (optional): its settings, its limits, Start; it runs while you fly your **approach waypoints** and ends
   at the Pause, which keeps the exposure it learned. Delete the block, down to its Pause, to fly the header's exposure.
4. **Leg 1:** survey settings, Start, **your leg 1 waypoints**, Pause (no photos on the turn).
5. **An exposure change** (optional): a Sensor item between the Pause and the next Start (here 1/2000 s). Change
   exposure only there, or from the ground station while paused: a running survey refuses changes.
6. **Leg 2:** settings, Start, **your leg 2 waypoints**; more legs repeat Pause, settings, Start, waypoints.
7. **End** (no more photos this flight), **Return to launch**.

Every Tri-Cam command is followed by a 0.1 s delay (`#112`): keep them.

Give the plan its own mission UUID (random; or 32 hex digits as a third argument), keeping the header's settings and
everything else in the file; the result is validated:

    python3 tricam_plan_check.py stamp examples/tricam_sample.plan my_survey.plan

Every image carries the UUID; after the upload the aircraft confirms the plan with its first eight digits
(`Tri-Cam: Plan 1A2B3C4D Loaded`), and at arming the Tri-Cam announces them (`Tri-Cam: Mission 1A2B3C4D sortie ...`).
Plans that keep the sample's UUID (`5A3B1E5A`) cannot be told apart in the data. Then open `my_survey.plan` in QGroundControl, replace the example waypoints with yours, save, and check it again
before uploading:

    python3 tricam_plan_check.py validate my_survey.plan

The aircraft checks the same rules before it allows arming and names the first problem by item number
(`PreArm: Tri-Cam: PLAN ERROR (...) item N`).

Things to know:

* **QGroundControl drops the comments** when it saves the plan (it keeps the items). Keep this README, or the sample,
  at hand.
* **Turn off camera triggering in QGroundControl's Survey tool.** It adds `#206` (trigger by distance), which a
  Tri-Cam plan must not contain: the aircraft refuses to arm.
* **The header's settings** (the survey settings and the starting exposure) cannot be changed by hand; settings can
  change in flight through Sensor and Series items between a Pause and a Start, as in the sample.
* **After an exposure change** the cameras need two frames to apply it; the Tri-Cam spends them itself (two discarded
  triggers) before the next Start. A single photo taken within about a second of a change may still show the old
  setting; every image file records the exposure actually used.
