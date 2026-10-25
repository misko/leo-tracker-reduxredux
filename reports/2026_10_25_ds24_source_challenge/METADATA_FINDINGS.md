# Independent-observable feasibility: exported evidence remains insufficient

This is a bounded metadata check of the already-used DS24-0010 and DS24-0013
fast-session exports, not a search of every raw recording or companion
authority. It reads no IQ, propagates no orbit and fits no position. The
current export fields do not by themselves establish an additional calibrated
timing, power or bearing observation suitable for the localization likelihood.
This narrows the immediate implementation options; it does not prove the
underlying corpus contains no usable independent information.

| Evidence reviewed | Available | What is still required before using it for position |
| --- | --- | --- |
| Both fast tracking exports | Integer candidate epoch and fractional epoch offset; sample counters; host monotonic/realtime brackets | An applicable transmitter-time/clock and ambiguity model. A detector's sample offset alone is not an authenticated transmit epoch or calibrated range. |
| Both fast tracking exports | Exact/control/margin detection scores | A justified conversion or calibration for received power and antenna response. These fields are detector scores, not a stored calibrated RSSI/bearing contract. |
| Both fast tracking exports | RF, channel, receiver, visit and original probe indexing | Calibrated installed pointing/phase centers and applicable synchronization authority. These identifiers alone do not provide an angular observation. |
| Published LT3D-004B installation authority | Nominal 40-degree included angle and CAD dimensions | Actual installed elevation and RF baseline are explicitly unknown; cable mapping is provisional. CAD positions do not certify the RF phase-center baseline. |
| Current recording synchronization contract | Explicit `phase_coherent=False` claim | A separately qualified phase/synchronization measurement before an inter-receiver phase likelihood. This contract restriction does not establish that every possible IQ-level estimator must fail. |

The inventory examines 13,470 probes/61,070 candidate records in 0010 and
13,418 probes/62,960 candidate records in 0013. All candidate records expose
the same eight non-null fields: candidate rank, fractional control/exact/margin
scores, fractional tracking CFO, integer epoch, fractional epoch offset and
the fractional-margin gate outcome. Candidate records compete within probes;
these counts are not independent GLRT winners or additional emitters.

The two exports have `source.timing=null` and an explicit `clock_anchor`
containing before/after host monotonic/realtime values and a sample counter.
The existing fast adapter already uses this anchor. A null adaptive-style
timing field is not evidence that native sample timing is absent or that the
recording is invalid. These are derived fast-session exports, identified by
their original `fast-` session ID and 10 MS/s data; the generic export's
`capture_mode` field is not used here to reclassify dataset members.

The next possible step would be a narrowly scoped lookup of the applicable
raw recording/pose/synchronization companions, if another observable requires
them. The present metadata does not authorize fabricating a bearing or range
constraint, extracting a broad new IQ campaign, or treating the two colocated
feeds as separated geolocation stations. No new RF collection is proposed.

[Inventory](metadata_inventory.json) contains the exact schemas, counts and
source hashes. [Extraction source](metadata_inventory.py) is read-only and
checks the expected fast-session/sample-rate identities. Successful extraction
took 0.468 seconds. Its first preparation attempted to count dictionary values
instead of keys and failed an internal count assertion before writing output;
the corrected key-counting operation produced the inventory. No scientific
observation, policy or original file changed.

Sources are the two original exported tracking contracts named in the
inventory, the current `fast_scan.py`, `fast_scan_native.py` and `recording.py`
contracts, and the documented LT3D-004B authority. The latter contains an
installation coordinate, but no coordinate is extracted by the inventory or
passed to either scientific branch. This is a schema/authority availability
check, not a physically calibrated information calculation.
