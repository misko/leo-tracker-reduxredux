# DS30-0003 lean rejection and final candidate support

DS30-0003 paid **8.874 s wall** for one lean attempt, then **34.367 s wall** for the ordinary named fallback on the same mixed packet. The lean path was initially admitted on healthy earlier samples, but failed **`repair_original_joint_pair_gate`** after one paid paired repair. A perfect free veto before any lean work would leave **91.264 s**, or only **1.292×** versus the measured installed 117.919 s, with all other time fixed. [Sealed attribution and clocks](measurements/ds30-0003-witness-attribution.json)

The repair removed 125 of 2,722 curved points, zero of 438 predictive points and two of 89 tracks, within its frozen 5% caps. After refit, both calibration arms still failed the same two *remaining* curved tracks. They have 123 incompatible points among the 2,597 retained curved points, with all 438 predictive points compatible. The failed components are distinct from the two already removed. Removing both sets would exclude **248 of the original 2,722 curved points (9.11%)**, beyond the actual limit of 136 points. The paired gate requires every retained track to pass. This arithmetic describes the recorded incompatibilities on the recorded support. It does not predict a second refit. [Repair and cap](blind_joint_repair.py)

| Disjoint cost inside the 50.208 s decision and publication phase | Wall (s) | CPU (s) |
| --- | ---: | ---: |
| Solver preparation | 3.198 | 2.464 |
| Rejected lean work before evidence | 8.874 | 8.837 |
| Paid ordinary fallback | 34.367 | 34.177 |
| Other work in the solve | 0.216 | 0.193 |
| Rendering | 1.389 | 1.311 |
| Remaining decision and publication | 2.164 | 1.482 |

The raw acquisition was a separate **47.946 s wall / 38.146 s CPU**. The failed lean branch includes a 3.414 s cold phase and a 0.499 s pair repair fit. An exact early stop after a failing first repair arm can therefore save at most the latter on this case. The nomination audit records one ordinary fallback and excluded speculative ranks and fit prefixes. It provides no proof that those prefixes could replace the named search. [Related post-fit early veto study](early-lean-refusal-0255.md)

## Which detector evidence the final mixed fit used

Both arms have the same ordered 2,905 candidate owner rows, and both observation-to-satellite maps reproduce their published digests. All rows join to exact signed native opportunities. The display reports retain 5,318 installed and 5,705 mixed unowned plot points with relative sample time, radio, visit, channel, CFO and margin. They lack absolute pilot epoch and track or satellite ownership. The plot times recover exact counters using the signed clock offset and match the reread signed native points. The final classification uses the original unique signed match of ≤250 Hz and ≤2 absolute samples in the same radio opportunity. [Original detector comparison](ds30-0003-native-agreement.md)

| Final candidate owners per arm | Matched installed peak | Candidate positive, installed empty | Both positive, outside signed match |
| --- | ---: | ---: | ---: |
| 8 ms short | 2,184 | 59 | 256 |
| 20 ms anchor | 374 | 15 | 17 |
| Total | **2,558** | **74** | **273** |

There were zero ambiguous or unjoinable owners. Only 74 of the 1,074 additional occupied candidate opportunities were owned in the final mixed fit. The installed report contains no original owner rows, so these counts cannot identify lost installed owners or allocate the position error to any group. The witness additionally preserves the failed lean branch’s track-level support and final candidate roles. The candidate owner roles and point-to-satellite digests refer to the published fallback.

Each of the three detailed NVMe output documents was read once. **2,488,888 logical bytes** charged **2,494,464 storage bytes** in a 15.2 ms idle read lease. The plot reports contain sufficient hardware time for a presence join. Their missing pilot epoch made an exact signed match require one additional scoped read of each original detector packet. Both byte digests verified. That lease read **10,200,355 logical bytes** and charged **10,207,232 storage bytes** in 73.9 ms. Both read leases used CPU3, nice 15 and idle I/O, and the final joins ran on the in-memory operands. The detailed documents are bound to their original run and terminal and have newly recorded full-file SHA-256 values. No original recording, orbit body, other-case result, survey or solver was accessed. [Attribution helper](ds30_0003_witness_attribution.py)
