# Station geometry observation log

This log records operator observations and experimental interventions alongside
the immutable, content-addressed geometry manifests. Announcement time does
not establish a capture-time orientation boundary. Append confirmations and
corrections explicitly; preserve the earlier observation and its uncertainty.

## 2026-09-23: planned 180-degree rotation of the r21 array

- **Announcement recorded:** approximately 2026-09-23 14:44 UTC.
- **Operator statement:** "im going to rotate the array 180degrees right now".
- **State:** intended immediate intervention; completion has not yet been confirmed.
- **Station / radio:** `station_gauss` / `radio_pluto_19f2` (r21).
- **Existing fixture:** `LT3D-001A`; nominal revision `lt3d-001a-nominal-v1`.
- **Existing geometry authority:**
  [gauss-r21-lt3d-001a-20260920-v1.json](gauss-r21-lt3d-001a-20260920-v1.json).
- **Requested change:** rotate the physical array by 180 degrees.
- **Unconfirmed details:** completion UTC, axis of rotation, absolute before/after
  azimuth, unchanged cable connections, and any accompanying tilt/height changes.
- **Experiment:** compare RX0/RX1 GLRT detection distributions on 2026-09-24 to
  the [pre-rotation eight-hour baseline](../../reports/2026_09_23_eight_hour_glrt_rotation_baseline.md).

The existing manifest maps RX0 to `rx_lnb_c` / `negative-x` and RX1 to `rx_lnb_d`
/ `positive-x`, but marks both slot mappings **provisional** because the physical
left/right cable trace has not been recorded. These are fixture-local slots;
a rigid rotation changes their world orientation without itself swapping their
local labels or electrical receiver identities. The manifest has no measured
world azimuth; RF boresight and phase-center fields are unmeasured.

The report's baseline window ends at 14:39:14 UTC, before this announcement.
Do not use 14:44 UTC as an exact post-rotation cutoff without confirmation.
Exclude recordings that overlap movement or the uncertain transition interval.
For the planned comparison, keep RX0/RX1 labels attached to the same electrical
chains and record any cable swap separately.

This note does not rewrite the published geometry manifest, assert a measured
orientation, or deploy a new capture-time geometry binding. A future measured
world-orientation record must carry its own evidence and validity boundary.
