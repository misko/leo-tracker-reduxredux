# Full roof validation of the sealed secant optimizer

Use the fixed 127 common DS26 and eight DS29 roof recordings. Adopt the six
sealed secant timing outputs and the eight disjoint secant confirmation outputs
only after checking their scientific source, original native and catalogue
digests, and request provenance. The remaining 121 recordings receive a single
fresh ordinary `v5_secant_fit` replay. The method is fixed at SHA-256
`17a5fbaf1d535115d69572fadacf5fa9427663d2622f33000ecf994303b1ddee` with all four
compact dependencies matching the earlier scientific source archive.

Submit the 121 cases in decreasing order of historical compact-projector
supervisor wall time, using ascending recording ID for ties. This scheduling
proxy uses only elapsed times from the authenticated projector archive. Use
eight workers on cores 12–19, with one numerical thread per worker. Run under
a detached supervisor, with at most 480 seconds per worker and 2,280 seconds
from launch for the whole replay. Reserve five seconds for returning the final
worker and writing its journal. A final attempted worker can receive a shorter
deadline. Keep all timeouts, failures, withheld positions and unattempted
recordings in the denominator. Do not retry or substitute a stock fix.

Both calibration arms start from complete stored native GLRT detections,
the original 25 km tile, the same causal orbital catalogue and the full
five-refresh compact-v5 policy. Bind same-input archived compact-projector
positions and the four original v5 options. Validate their original role
requests and actual archived outputs separately from candidate inference.
Seal all 135 candidate and stock rows before opening independent positions.

Report position errors, published counts, P50/P95/maximum, paired error
within 5% and 10%, and largest regressions for DS26 and DS29, with both
calibration arms. Report conditional RF RMS independently. Keep fresh full
panel worker times, prior eight confirmation times, prior six paired times,
and historical compact-projector times explicitly scoped. No new RF is
collected.
