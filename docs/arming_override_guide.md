# Arming Blocked by the Tri-Cam, and the Arming Override

Since KB2040 r192, arming is blocked while any camera channel is not ready, with or without a plan.

---

## 1. If arming is refused: "Tri-Cam: not ready: ..."

A channel is not ready when its node does not answer (no SD card, halted, offline), its camera is missing, or its card
is unusable (SD error or too slow, 1-bit bus, filesystem error). QGroundControl shows
`PreArm: Tri-Cam: not ready: OblqRt ...`, and the Tri-Cam says why every 8 s, for example
`Tri-Cam: blocked: OblqRt off,Nadir cam` (`off`: no node; `cam`: no camera; `SD`: storage).

Fix it on the ground: insert the cards, reseat the camera or the card.

A plan with a problem is refused differently: `PreArm: Tri-Cam: PLAN ERROR (...) item N`. Check plans before uploading
with the plan development kit ([`plan_development/`](../plan_development/)).

---

## 2. To fly anyway, deliberately: the arming override

Send `TC_ARM_OVERRIDE` (command 31033 to component 100, p1 = 6283) from the ground station. It allows the next arming
only, and the arming is recorded as `Tri-Cam AUDIT: Armed, not ready (override)`. The flight will not have all its
images. p1 = 0 cancels a pending override.

With QGroundControl, [`TriCamActions.json`](TriCamActions.json) makes both a Fly View action:

1. Copy `docs/TriCamActions.json` into the `MavlinkActions` folder of QGroundControl's save location (on Linux
   `~/Documents/QGroundControl/MavlinkActions`).
2. Select it under Application Settings (Fly View, custom actions).
3. In the Fly View's Action menu: "Tri-Cam: allow arming without cameras" (with its confirmation slider), or
   "Tri-Cam: cancel the arming override".
