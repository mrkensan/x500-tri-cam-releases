# Tri-Cam Plan Development Guide

For the author of software that generates QGroundControl `.plan` files for an aircraft carrying the Tri-Cam. It
describes what a Tri-Cam plan must contain, how each item is encoded (bit-exact), what the Tri-Cam does with it in
flight, and how to check your output with this kit before it reaches an aircraft. If a command or a behaviour is not
described here, a plan must not rely on it.

This guide and the kit match **Plan Loader build 5**, plan interface version 1.

| In this kit | What it is for |
|---|---|
| `PLAN_DEVELOPMENT_GUIDE.md` | This guide |
| `tricam_plan_check.py` | The validator: the rules the aircraft checks, run on your `.plan` file (section 9) |
| `vectors/encoder_vectors.json` | Bit-exact vectors for your encoder: words, headers, fingerprints, conversions |
| `examples/` | Plans that pass every rule, to compare your output with |
| `test_plans/` | One plan per mistake the rules catch, with the expected findings (`expected_findings.json`) |

## 1. How a Tri-Cam plan works

The Tri-Cam is a three-camera payload that the flight controller (ArduPilot Copter, Plane or Rover) drives as a
MAVLink camera. A **Tri-Cam plan** is an ordinary mission with three kinds of Tri-Cam content:

1. **The header**: a short run of `#217` items before the first navigation item. It marks the plan as a Tri-Cam plan
   and carries the **mission UUID** and, optionally, the survey's starting settings (section 4).
2. **Tri-Cam commands** placed among the navigation items: settings, Start, Pause and End of the survey, single
   shots (section 5).
3. **A pacing delay** (`#112`) after every Tri-Cam command (section 3).

Before arming, the **Plan Loader** (part of the Tri-Cam installation on the flight controller) reads the uploaded
mission, checks it against the rules of section 8, hands the header to the Tri-Cam and confirms that the Tri-Cam
holds the same header (by its fingerprint). Then it allows arming and posts `Tri-Cam: Plan 00112233 Loaded` (the
first eight hex digits of the mission UUID), or it blocks arming and names the first problem, for example
`PreArm: Tri-Cam: PLAN ERROR (PACING) item N`. After arming nothing is checked again; in AUTO the flight controller
runs the mission and sends each Tri-Cam command to the Tri-Cam as it reaches it.

A plan **without a header** is not a Tri-Cam plan: arming is allowed, but no survey can run (the Tri-Cam takes single
shots only, under a stand-in identity). Survey commands in such a plan are an error (`NO_HEADER`).

## 2. The plan file

A Tri-Cam plan is a QGroundControl plan file (JSON, `"fileType": "Plan"`). Write everything else in the file as your
tool already does; for the Tri-Cam:

* **Simple items only.** Every Tri-Cam item, and every item you want checked, is a `"type": "SimpleItem"` with
  `command`, `params` (exactly seven numbers), `frame`, `autoContinue` and `doJumpId`. QGroundControl's patterns
  (complex items such as Survey) are expanded only when QGroundControl uploads the plan, so neither you nor the
  validator can check what they contain; the validator says so in a note.
* **Header and command items** use `"frame": 2` (`MAV_FRAME_MISSION`) and `"autoContinue": true`. Unused parameters
  are `0`. (The validator does not check `frame` or `autoContinue`.)
* **Exact values.** Every Tri-Cam parameter is an integer below 2^24 (16,777,216) or one of the delays of section 3.
  Write integers exactly (`5505280` or `5505280.0`), never rounded, never in shortened scientific notation and
  never `null`. Values below 2^24 survive the 32-bit floats of MAVLink exactly: QGroundControl 5.1.5 was verified to
  load, save and upload every test value up to 16,777,215 bit-exactly.
* **Item numbers.** The aircraft numbers mission items from 1 (home is 0): "item N" in a message is
  `mission.items[N-1]` in the file. The validator uses the same numbers.
* **What QGroundControl changes when it saves a plan** (observed with 5.1.5): it drops keys it does not know (the
  annotation block of section 4.7, any `_comment`), writes a NaN parameter as `null` (for example Pause p2–p7) and may
  add keys of its own. None of this changes the Tri-Cam content; the validator reads `null` as NaN, which is what the
  aircraft receives.
* **Commands the flight controller refuses at upload.** With ArduCopter 4.7.2 a mission containing `#180`, `#204`,
  `#214`, `#246`, `#512`, `#530`, `#533` or `#2003` fails to upload as a whole (observed; the validator does not check
  this). Do not emit them.

If you also let users edit plans in QGroundControl's Survey tool, its camera triggering must be off: it adds `#206`,
which a Tri-Cam plan must not contain.

## 3. Plan structure and timing

A typical Tri-Cam plan, in order:

1. **Header** (`#217` items), together and before the first navigation item.
2. **Takeoff.**
3. *Optional* **AEC_Cal**: a Series word with exposure mode 3 (and a Sensor word with AEC bounds), Start, the approach
   waypoints, Pause (section 6).
4. **Each survey leg**: settings if they change (only here, between a Pause and the next Start), Start, the leg's
   waypoints, Pause (no photos on the turn).
5. **End** (`#532`, p1 = 4) before the final navigation item.
6. **Return to launch** or the landing (the final navigation item).

Every Tri-Cam command is followed by its `#112` delay. `examples/tricam_sample.plan` is this layout with every item
explained (`_comment` keys); `examples/example_survey.plan` is the worked example of Appendix A.

**When items run** (ArduPilot AUTO):

* Items before the first navigation item run when AUTO starts, together with the takeoff.
* Items after a navigation item run when that item is reached, while the aircraft flies on to the next one; they do
  not delay navigation. If the aircraft reaches the next navigation item first, the items not yet run are skipped:
  keep each group of commands short (a group's delays add up).
* After the **final navigation item** only the first following item runs. A Tri-Cam command after it is an error
  (`AFTER_NAV`).

**Pacing.** Follow every Tri-Cam command with a `#112` (`CONDITION_DELAY`) of **0.1 s**, or **0.25 s** after a
single shot (`#2000`). Without a delay the flight controller sends consecutive commands within milliseconds of each
other. The validator requires the delay between two Tri-Cam commands that have no navigation item between them: at
least 0.1 s, and at least 0.25 s between two single shots (`PACING`). A delay before a navigation item is harmless.

**End before the final navigation item.** A plan that starts a survey must end it, `#532` p1 = 4, before its final
navigation item (`NO_END`). End stops the capture and has the cameras write and sync their storage while the aircraft
is still flying. A plan's own Return-to-Launch item keeps the flight mode at AUTO and ends nothing, and ArduPilot
reports a plan complete only when its last item finishes (at the landing), too late for that. On a Plane that lands
automatically, put End before the landing sequence.

## 4. The header

### 4.1 Stanzas

The header is a run of consecutive `#217` (`DO_SEND_SCRIPT_MESSAGE`) items, one **stanza** per item:

| Item param | Content |
|---|---|
| p1 | stanza type × 256 + position (type in the high byte, position in the low byte; the Header is position 0) |
| p2, p3, p4 | the stanza's three 24-bit words W0, W1, W2 |
| p5, p6, p7 | 0 |

The stanzas, in this order:

| Type | Position | Stanza | Required | W0 | W1 | W2 |
|---|---|---|---|---|---|---|
| 1 | 0 | Header | yes | magic `0x54`, version `0x01`, flags `0x00` (= `0x540100`) | 0 | number of stanzas after the Header, Check included |
| 2 | 1 | UUID-A | yes | UUID bytes 0–2 | bytes 3–5 | bytes 6–8 |
| 3 | 2 | UUID-B | yes | UUID bytes 9–11 | bytes 12–14 | byte 15, then `0x00 0x00` |
| 4 | 3 | Series | no, at most one | Series Capture Config word (5.1) | 0 | 0 |
| 5 | next | Sensor | no, at most three | Sensor Config word (5.2) | 0 | 0 |
| 6 | last | Check | yes | 16-bit fingerprint (4.3) | 0 | 0 |

Positions run 0, 1, 2 … without gaps, so a header has 4 to 8 items; the Header's W2 is the item count minus one. The
Series and Sensor stanzas carry the same words as the `#531` commands; they set what the survey starts with. If a
setting is sent again later as a command, the Tri-Cam uses the one it received last.

### 4.2 Packing

Three bytes per word, most significant byte first. UUID byte 0 is the first two hex digits of the UUID as it is
written (`00112233-4455-…` has byte 0 = `0x00`, byte 1 = `0x11`). So UUID-A's W0 is bytes 0–2 as one big-endian
24-bit number.

### 4.3 Fingerprint

CRC-16/CCITT-FALSE (polynomial `0x1021`, initial value `0xFFFF`, no reflection, no final XOR; the check value of the
ASCII string `123456789` is `0x29B1`) over every stanza before Check, in order: for each stanza its p1 as two bytes,
then W0, W1 and W2 as three bytes each, all most significant byte first. Check is not included. Appendix A shows the
bytes and the result for the worked example.

### 4.4 Rules

The Plan Loader reads the header rigidly and does not repair an almost-correct one; any of these blocks arming with
`Tri-Cam: PLAN INVALID (<reason>)`:

* The order above is mandatory, with positions without gaps (`ORDER`); the Header's count matches and Check is last
  (`COUNT`).
* The stanzas are consecutive, with no other item between them, and all come before the first navigation item
  (`PLACEMENT`).
* The version is 1 (`VERSION`); reserved words, the flags and UUID-B's padding are 0 (`RESERVED`).
* The UUID is not all `0x00` or all `0xFF` (`UUID`).
* Embedded Series and Sensor words pass their check bits and ranges, and the header's Series word does not select
  exposure mode 3: AEC_Cal is started in flight, not set up in the header (`WORD`).
* There is one Header (`DUPLICATE`), and no stanza type other than 1–6 (`STANZA`).
* The fingerprint matches (`CHECK`).

Other `#217` items, outside the header's run, are not Tri-Cam items and are ignored. A plan without a Header stanza
(type 1 with the magic `0x54`) has no header.

### 4.5 The mission UUID

The mission UUID (128 bits) identifies the plan; there is no other plan identity. Generate a new random UUID for every
plan you produce (for example a version 4 UUID), and keep it when the same plan is flown again. Every image the
Tri-Cam takes carries it, and at arming the Tri-Cam announces its first eight hex digits
(`Tri-Cam: Mission 00112233 sortie ...`). Plans that share a UUID cannot be told apart in the data.

### 4.6 Changing a plan

Do not edit a generated Tri-Cam item by hand: its check bits or the fingerprint would no longer match, and the plan is
refused. Regenerate instead. (`tricam_plan_check.py stamp` puts a new UUID into an existing plan's header and
recomputes it; the rest of the file is kept.)

### 4.7 The annotation block (optional)

So that a person opening the file can tell what it is, a generator may add an `_tricam` object at the top level of the
file and a one-line `_comment` inside `mission`. The flight controller never sees them, the Tri-Cam never reads them,
and QGroundControl drops them when it saves the plan:

```json
{
  "fileType": "Plan",
  "_tricam": {
    "format": "Tri-Cam plan",
    "interfaceVersion": 1,
    "uuid": "00112233-4455-6677-8899-aabbccddeeff",
    "generator": "your tool and its version",
    "created": "2026-11-20T00:00:00Z",
    "description": "free text",
    "warning": "DO NOT EDIT. Tri-Cam reads the #217 header items in the mission, not this block."
  },
  "mission": {
    "_comment": "DO NOT EDIT! The first six #217 items are Tri-Cam Config.",
    "items": ["..."]
  }
}
```

`uuid` is the mission UUID in lowercase 8-4-4-4-12 form and `interfaceVersion` the header version; `created` and
`description` are optional. If either disagrees with the header, the validator warns (`ANNOT_UUID`, `ANNOT_VER`).

## 5. Tri-Cam commands

| Command | Item | Parameters | What it does |
|---|---|---|---|
| Series Capture Config | `#531` (`SET_CAMERA_ZOOM`) | p1 = 1, p2 = word (5.1) | Survey interval and cadence, exposure mode, compression, AEC_Cal length |
| Sensor Config | `#531` (`SET_CAMERA_ZOOM`) | p1 = 2, p2 = word (5.2) | Exposure time and ISO: fixed values or AEC bounds, one camera or all |
| Start Survey | `#2500` (`VIDEO_START_CAPTURE`) | p1 = 0 | Starts the survey, or resumes it after a Pause; begins AEC_Cal if exposure mode 3 is in force |
| Pause Survey | `#2501` (`VIDEO_STOP_CAPTURE`) | p1 = 0 | Pauses the survey, or ends AEC_Cal; settings, identity and image numbering are kept |
| End Survey | `#532` (`SET_CAMERA_FOCUS`) | p1 = 4, p2 = 0 | Ends the survey: capture stops, images are written and storage synced; no capture until disarm |
| Single shot | `#2000` (`IMAGE_START_CAPTURE`) | p1 = 0, p2 = 0, p3 = 1 | One synchronized photo from all cameras, outside a survey |
| Pacing delay | `#112` (`CONDITION_DELAY`) | p1 = seconds | After every Tri-Cam command (section 3) |

All other parameters are 0. Start and Pause need p1 = 0 (`P1`). In a Tri-Cam plan these are errors: `#2000` in any
other form (the flight controller would run a photo series itself as repeated single shots: `SINGLE`), `#2001`
(`STOP`), `#203` (`DIGICAM`) and `#206` (`TRIG_DIST`). `#531` with p1 other than 1 or 2 and `#532` with p1 other than
4 are reserved: do not emit them (the validator does not flag them; the Tri-Cam ignores them).

### 5.1 Series Capture Config word

Bit 0 is the least significant bit.

| Bits | Field | Values |
|---|---|---|
| 0–7 | `interval_n` | 0…250: interval = 0.500 + 0.014 × n seconds (0.500–4.000 s); 251–255 reserved |
| 8–11 | `max_scale` | 0…15: in adaptive cadence the period may stretch to interval × (1 + m/15), 100 %…200 %; ignored in fixed cadence |
| 12 | `adaptive` | 0 fixed cadence, 1 adaptive cadence |
| 13–14 | `exposure_mode` | 0 no change, 1 fixed exposure, 2 AEC during the survey, 3 AEC_Cal (section 6) |
| 15 | `compression` | 0 uncompressed, 1 DPCM-compressed images |
| 16–19 | `aec_cal_frames` | 0…15: 0 = the default; with exposure mode 3 it must be 0 or at least 4 |
| 20–23 | check | 4-bit CRC (5.3) |

The interval is a request: the Tri-Cam may lengthen it to what its storage sustains, and reports the value it uses.

### 5.2 Sensor Config word

| Bits | Field | Values |
|---|---|---|
| 0–8 | `exposure_lines` | 0 = no change; 1…362 sensor lines (one line = 27.6345238 µs, about 1/36,200 s to 1/100 s) |
| 9–14 | `iso_step` | 0 = no change; 2…44: ISO = 50 × step (100…2200) |
| 15 | `bounds` | 0 = fixed values; 1 = AEC bounds (exposure = the longest allowed, ISO = the highest allowed) |
| 16–17 | `channel` | camera 0 ObliqueRt, 1 Nadir, 2 ObliqueFwd; 3 = all cameras |
| 18–23 | check | 6-bit CRC (5.3) |

A fixed-values word applies with exposure mode 1, a bounds word with exposure modes 2 and 3. The Tri-Cam ignores a
word that does not match the exposure mode in force when the survey starts, without a message; the validator reports
it (`SENSOR`, section 6). A word addressed to a camera that is offline is accepted and applied to the cameras that are
online; the Tri-Cam does not remember it for the offline one.

### 5.3 Check bits

A bitwise CRC, most significant bit first, over the word's data bits (bits 0–19 of a Series word, bits 0–17 of a
Sensor word), seeded so that an all-zero word never passes:

| Word | Width | Polynomial | Initial value | Data bits |
|---|---|---|---|---|
| Series Capture Config | 4 | `0x03` | `0x0F` | 20 |
| Sensor Config | 6 | `0x03` | `0x3F` | 18 |

```text
reg = init
for i = nbits-1 downto 0:
    top = (reg >> (width-1)) & 1
    reg = (reg << 1) & ((1 << width) - 1)
    if top XOR ((data >> i) & 1): reg ^= poly
check = reg
word = data | (check << nbits)
```

### 5.4 Conversions

* Interval: n = round((seconds − 0.5) / 0.014); the interval is then 0.5 + 0.014 × n (1.5 s gives n = 71, 1.494 s).
* Exposure: lines = round(µs / 27.6345238); for a shutter of 1/d s, lines = round(10⁶ / d / 27.6345238) (1/1000 s
  gives 36 lines, 1/2000 s 18).
* ISO: step = ISO / 50, ISO a multiple of 50 from 100 to 2200 (ISO 400 gives 8).

`vectors/encoder_vectors.json` holds these conversions and words with their fields, to test your encoder against.

## 6. What the commands do in flight

The Tri-Cam's survey is in one of four states. Each plan command acts as follows; "error" means the validator and the
Plan Loader refuse the plan, because the Tri-Cam would refuse or ignore the command in flight.

| State | Config (`#531`) | Start (`#2500`) | Pause (`#2501`) | Single shot (`#2000`) | End (`#532`) |
|---|---|---|---|---|---|
| **Idle** (armed, no survey running; also after a Pause) | applied | → Active, or → AEC_Cal if exposure mode 3 is in force | nothing | photo | → Ended |
| **AEC_Cal** | error `CAL_BUSY` | error `CAL_BUSY` | ends AEC_Cal → Idle | error `CAL_BUSY` | ends AEC_Cal → Ended |
| **Active** (survey running) | error `REFUSED` | error `NOOP` | → Idle | error `REFUSED` | → Ended |
| **Ended** (until disarm) | error `REFUSED` | error `REFUSED` | nothing | error `REFUSED` | nothing |

From this follow the rules a generator applies:

* **Settings change only while Idle**: in the header, before the first Start, or between a Pause and the next Start.
* **Single shots only while Idle**, never during a survey leg or AEC_Cal.
* **Sensor words must suit the exposure mode in force at each Start**: fixed values with mode 1, bounds with modes 2
  and 3 (`SENSOR`). The last word sent for a camera is the one that counts; the mode is the header's or the last
  Series word's (mode 0 in a word keeps the current one; without any Series word it is 1).
* **AEC_Cal** (automatic exposure calibration): a Series word with exposure mode 3, then Start. The Tri-Cam captures
  frames at the interval, learns an exposure from them and discards those images. Put waypoints between its Start and
  its Pause so that it runs while the aircraft flies (for example the approach to the first leg). It ends when its
  frames are done or at the Pause, whichever comes first (a Pause after it has ended does nothing): with at least 4
  frames taken it keeps what it learned as a fixed exposure, otherwise it restores the exposure it had before; either
  way the exposure mode is 1 (fixed) afterwards, and the next Start begins the survey. Always put the Pause before the
  next Start. Its frame count is the word's `aec_cal_frames`, or 8 for 0. If a Pause follows its Start with only delays between them, the validator
  warns when the delays do not cover the frames (`CAL_SHORT`). The default of 8 frames and the minimum of 4 are
  provisional.
* **After an exposure change** the cameras need two frames to apply it; the Tri-Cam spends them itself (two discarded
  triggers) before the next Start. A single shot within about a second of a change may still show the old setting;
  every image file records the exposure actually used.

The survey also ends by itself (→ Ended) when the pilot leaves AUTO after a Start, on a return flight mode (RTL, LAND,
SMART_RTL and their Plane and Rover equivalents) and at touchdown, each once it has held for more than 2 seconds, and
when the flight controller's link is lost (no heartbeat for 5 seconds while armed). A plan does not rely on these: it
ends its survey itself (section 3).

## 7. Constants, defaults and limits

<!-- BEGIN GENERATED: constants (build_kit.py; do not edit by hand) -->
| Item | Value |
|---|---|
| Header magic, interface version | `0x54` (`T`), 1 |
| Stanza types | Header 1, UUID-A 2, UUID-B 3, Series 4, Sensor 5, Check 6 |
| Optional stanzas | at most one Series, at most 3 Sensor |
| Pacing (`#112` p1) | 0.1 s after every Tri-Cam command; 0.25 s between two `#2000` |
| Interval | code n = 0…250: 0.500 + 0.014 × n s (0.500…4.000 s) |
| Adaptive maximum | m = 0…15: base × (1 + m/15), 100 %…200 % of the interval |
| Exposure | 1…362 sensor lines, one line = 27.6345238 µs (362 lines ≈ 1/100 s, the slowest shutter allowed); 0 = no change |
| ISO | step 2…44: ISO = 50 × step (100…2200); 0 = no change |
| AEC_Cal frames | 0 = the default (8), otherwise at least 4 (and at most 15); at least 4 frames are needed to keep what it learned |
| Cameras (Sensor word) | 0 ObliqueRt, 1 Nadir, 2 ObliqueFwd, 3 all |
| Without a Series word | interval code 36 (1.004 s), fixed cadence, adaptive maximum 15, exposure mode 1 (fixed), uncompressed, AEC_Cal frames 0 (the default) |
| Navigation items (`command`) | `16`, `17`, `18`, `19`, `20`, `21`, `22`, `82`, `92`, `93`, `94` |
| Not allowed in a Tri-Cam plan | `#2001`, `#203`, `#206`; `#2000` other than the single shot (p1 = 0, p2 = 0, p3 = 1) |
<!-- END GENERATED: constants -->

Without a header no survey runs. With a header but no Series stanza and no Series word, a survey runs with the
settings of the row "Without a Series word"; without a Sensor word each camera keeps its current exposure.

## 8. The rules the aircraft checks

The Plan Loader checks every rule below before it allows arming; the validator checks the same rules. An **error**
blocks arming: it is something the Tri-Cam or the flight controller would refuse or ignore in flight, or that breaks
the plan's execution. A **warning** is an estimate that depends on the flight and never blocks arming. The aircraft
shows the first error (`PreArm: Tri-Cam: ...`) and `Tri-Cam: N more plan errors` for the rest.

<!-- BEGIN GENERATED: rules (build_kit.py; do not edit by hand) -->
| Code | Rule | Severity | On the aircraft |
|---|---|---|---|
| `ORDER` | H-ORDER | error | `Tri-Cam: PLAN INVALID (ORDER)` |
| `COUNT` | H-COUNT | error | `Tri-Cam: PLAN INVALID (COUNT)` |
| `CHECK` | H-CHECK | error | `Tri-Cam: PLAN INVALID (CHECK)` |
| `UUID` | H-UUID | error | `Tri-Cam: PLAN INVALID (UUID)` |
| `VERSION` | H-VERSION | error | `Tri-Cam: PLAN INVALID (VERSION)` |
| `WORD` | H-WORD | error | `Tri-Cam: PLAN INVALID (WORD)` |
| `RESERVED` | H-RESERVED | error | `Tri-Cam: PLAN INVALID (RESERVED)` |
| `STANZA` | H-STANZA | error | `Tri-Cam: PLAN INVALID (STANZA)` |
| `DUPLICATE` | H-DUPLICATE | error | `Tri-Cam: PLAN INVALID (DUPLICATE)` |
| `PLACEMENT` | H-PLACEMENT | error | `Tri-Cam: PLAN INVALID (PLACEMENT)` |
| `NO_HEADER` | P-NO-HEADER | error | `Tri-Cam: PLAN ERROR (NO_HEADER) item N` |
| `NO_END` | P-NO-END | error | `Tri-Cam: PLAN ERROR (NO_END)` |
| `SINGLE` | P-SINGLE-FORM | error | `Tri-Cam: PLAN ERROR (SINGLE) item N` |
| `STOP` | P-FORBIDDEN-2001 | error | `Tri-Cam: PLAN ERROR (STOP) item N` |
| `DIGICAM` | P-FORBIDDEN-203 | error | `Tri-Cam: PLAN ERROR (DIGICAM) item N` |
| `TRIG_DIST` | P-FORBIDDEN-206 | error | `Tri-Cam: PLAN ERROR (TRIG_DIST) item N` |
| `AFTER_NAV` | P-AFTER-NAV | error | `Tri-Cam: PLAN ERROR (AFTER_NAV) item N` |
| `PACING` | P-PACING | error | `Tri-Cam: PLAN ERROR (PACING) item N` |
| `P1` | P-START-P1 | error | `Tri-Cam: PLAN ERROR (P1) item N` |
| `BAD_WORD` | P-BAD-WORD | error | `Tri-Cam: PLAN ERROR (BAD_WORD) item N` |
| `CAL_BUSY` | P-CAL-BUSY | error | `Tri-Cam: PLAN ERROR (CAL_BUSY) item N` |
| `CAL_BUSY` | P-CAL-SINGLE | error | `Tri-Cam: PLAN ERROR (CAL_BUSY) item N` |
| `REFUSED` | P-REFUSED | error | `Tri-Cam: PLAN ERROR (REFUSED) item N` |
| `NOOP` | P-START-NOOP | error | `Tri-Cam: PLAN ERROR (NOOP) item N` |
| `SENSOR` | P-SENSOR-MODE | error | `Tri-Cam: PLAN ERROR (SENSOR) item N` |
| `CAL_SHORT` | P-CAL-SHORT | warning | `Tri-Cam: Plan warning (CAL_SHORT) item N` |
| `ANNOT_UUID` | F-ANNOTATION-UUID | warning | (file only: the aircraft never sees the file) |
| `ANNOT_VER` | F-ANNOTATION-VERSION | warning | (file only: the aircraft never sees the file) |
<!-- END GENERATED: rules -->

### What each finding means and how to fix it

* `ORDER`, `COUNT`, `RESERVED`, `STANZA`, `DUPLICATE`, `VERSION`: the header is not laid out as in 4.1. Build it
  exactly as there: one Header, the stanzas in order, positions without gaps, the right count, unused words 0.
* `CHECK`: the fingerprint does not match the stanzas: compute it as in 4.3 after every other stanza is final.
* `UUID`: the UUID is all `0x00` or all `0xFF`: generate a random one (4.5).
* `WORD` (header): a Series or Sensor stanza's word fails its check or range, or the header's Series word selects
  exposure mode 3. Encode words as in 5.1–5.3; start AEC_Cal in flight (section 6), not from the header.
* `PLACEMENT`: the header items are not consecutive or come after the first navigation item: put them together at the
  start of the mission.
* `NO_HEADER`: survey commands in a plan without a header: add the header, or remove the survey commands.
* `NO_END`: the plan starts a survey but has no End before its final navigation item: add `#532` p1 = 4 and its delay
  before the last navigation item (section 3).
* `SINGLE`: a `#2000` that is not exactly p1 = 0, p2 = 0, p3 = 1: use the single shot, or a survey for repeated photos.
* `STOP`, `DIGICAM`, `TRIG_DIST`: `#2001`, `#203` or `#206` in a Tri-Cam plan: remove it (for QGroundControl's Survey
  tool, turn its camera triggering off).
* `AFTER_NAV`: a Tri-Cam command after the final navigation item would not run: move it before that item.
* `PACING`: too little `#112` delay between two Tri-Cam commands: follow every command with 0.1 s (0.25 s after a
  single shot). The text names the earlier command.
* `P1`: Start or Pause with p1 other than 0: write 0.
* `BAD_WORD`: a `#531` word fails its check bits or a range (the text says which): encode it as in 5.1–5.3; never
  edit a word by hand.
* `CAL_BUSY`: a Config word, a Start or a single shot while AEC_Cal runs: put AEC_Cal's Pause before it. The text
  names the Start that began AEC_Cal.
* `REFUSED`: a command the survey's state refuses (section 6), such as a Config word while a survey leg runs or any
  command after End: move it to where the survey is Idle (between a Pause and a Start), or remove it.
* `NOOP`: a Start while the survey is already running does nothing: add the Pause that should precede it, or remove it.
* `SENSOR`: a Sensor word that does not suit the exposure mode in force at a Start, which the Tri-Cam would ignore:
  use fixed values with mode 1, bounds with modes 2 and 3. The text names the word (an item, or the header's stanza).
* `CAL_SHORT` (warning): a Pause ends AEC_Cal after only delays, shorter than its frames need: put waypoints between
  its Start and its Pause, or accept the shorter run.
* `ANNOT_UUID`, `ANNOT_VER` (warnings, file only): the annotation block disagrees with the header: write the header's
  UUID and version into it (4.7).

## 9. Validating your output

`tricam_plan_check.py` needs Python 3.8 or later and nothing else.

    python3 tricam_plan_check.py validate my.plan
    python3 tricam_plan_check.py validate my.plan --json

The exit status is 0 when the plan has no errors (warnings are allowed), 1 when it has errors, and 2 when the file
cannot be read as a plan (not JSON, no `mission.items`, an item without seven numeric parameters). The text output
names each finding with its level, item number, rule and explanation, and the message the aircraft would show. The
JSON output carries the same; for `test_plans/10_missing_112_between_commands.plan`, saved as `my.plan`:

<!-- BEGIN GENERATED: json-example (build_kit.py; do not edit by hand) -->
```json
{
  "file": "my.plan",
  "plan_loader_build": 5,
  "result": "FAILED",
  "errors": 1,
  "warnings": 0,
  "header": {
    "status": "OK",
    "mission_uuid": "00112233-4455-6677-8899-aabbccddeeff",
    "fingerprint": 16726,
    "items": 6,
    "plan_loaded_message": "Tri-Cam: Plan 00112233 Loaded"
  },
  "findings": [
    {
      "rule": "P-PACING",
      "code": "PACING",
      "level": "ERROR",
      "item": 9,
      "text": "fewer than 0.1s of #112 delay since previous Tri-Cam command (item 8)",
      "message": "Tri-Cam: PLAN ERROR (PACING) item 9"
    }
  ],
  "notes": []
}
```
<!-- END GENERATED: json-example -->


`result` is `OK` or `FAILED` (`UNREADABLE`, with an `error` text, for exit status 2). `header.status` is `OK`,
`INVALID` (with a `reason`) or `NO_HEADER`. A finding's `item` is the mission item number, or `null` for the plan or
the header as a whole; `message` is `null` for a file-only finding. `notes` say what was not checked.

**A workflow that catches problems early:**

1. Unit-test your encoder against `vectors/encoder_vectors.json`: every word from its fields, both headers with
   their fingerprints and the bytes the fingerprint is computed over, the CRC check value and the conversions.
2. Validate every plan your tool produces: zero errors is required.
3. Compare your output with `examples/`; run the validator over `test_plans/` to see each mistake the rules catch and
   check that your tool never produces one (`test_plans/expected_findings.json` lists what each plan reports).
4. Load the plan in QGroundControl, save it, and validate the saved copy again (section 2 says what QGroundControl
   changes).
5. On the aircraft, after uploading: `Tri-Cam: Plan 00112233 Loaded` with your UUID's first eight digits confirms that
   the Tri-Cam holds your header.

**Generator checklist:** header first and complete (4.1–4.4), a new UUID per plan (4.5), words encoded with their
check bits (5.1–5.3), settings and single shots only while Idle (section 6), a `#112` after every Tri-Cam command
(section 3), End before the final navigation item, no `#2001`, `#203`, `#206` or other `#2000` forms, and zero errors
from the validator.

## Appendix A. Worked example

The header of `examples/example_survey.plan` (also in `vectors/encoder_vectors.json`, `header`):

<!-- BEGIN GENERATED: worked-example (build_kit.py; do not edit by hand) -->
Mission UUID `00112233-4455-6677-8899-aabbccddeeff`.

**Series word**: interval code 71 (1.494 s), adaptive maximum 15, cadence 1 (adaptive), exposure mode 2 (AEC), compression 1 (DPCM), AEC_Cal frames 0. Data bits 0–19 = `0x0DF47`; check (bits 20–23) = `0x9`; word = `0x90DF47` = 9494343.

**Sensor word**: 36 lines (1/1000 s), ISO step 8 (ISO 400), bounds 1 (AEC bounds), camera 3 (all). Data bits 0–17 = `0x39024`; check (bits 18–23) = `0x0D`; word = `0x379024` = 3641380.

**The header** (one `#217` item per row; p5–p7 are 0):

| Stanza | p1 (type × 256 + position) | p2 = W0 | p3 = W1 | p4 = W2 |
|---|---|---|---|---|
| Header | 256 (`0x0100`) | 5505280 (`0x540100`) | 0 (`0x000000`) | 5 (`0x000005`) |
| UUID-A | 513 (`0x0201`) | 4386 (`0x001122`) | 3359829 (`0x334455`) | 6715272 (`0x667788`) |
| UUID-B | 770 (`0x0302`) | 10070715 (`0x99AABB`) | 13426158 (`0xCCDDEE`) | 16711680 (`0xFF0000`) |
| Series | 1027 (`0x0403`) | 9494343 (`0x90DF47`) | 0 (`0x000000`) | 0 (`0x000000`) |
| Sensor | 1284 (`0x0504`) | 3641380 (`0x379024`) | 0 (`0x000000`) | 0 (`0x000000`) |
| Check | 1541 (`0x0605`) | 16726 (`0x004156`) | 0 (`0x000000`) | 0 (`0x000000`) |

**Fingerprint**: CRC-16/CCITT-FALSE over these 55 bytes (each stanza before Check: p1 as 2 bytes, then W0, W1, W2 as 3 bytes each, most significant byte first):

    0100540100000000000005 0201001122334455667788 030299AABBCCDDEEFF0000 040390DF47000000000000 0504379024000000000000

gives `0x4156` = 16726, the Check stanza's W0. The aircraft confirms this plan with `Tri-Cam: Plan 00112233 Loaded`.

As the first item of a plan file:

```json
{"autoContinue": true, "command": 217, "doJumpId": 1, "frame": 2, "params": [256, 5505280.0, 0.0, 5.0, 0.0, 0.0, 0.0], "type": "SimpleItem"}
```
<!-- END GENERATED: worked-example -->

The rest of the plan: Takeoff; AEC_Cal (a Series word with exposure mode 3 and 6 frames, the Sensor bounds, Start,
two waypoints, Pause); a Series word back to AEC, Start, the first leg's waypoints, Pause; the same Series word, Start,
the second leg; End; Return to launch. Each Tri-Cam command is followed by a 0.1 s `#112`.
