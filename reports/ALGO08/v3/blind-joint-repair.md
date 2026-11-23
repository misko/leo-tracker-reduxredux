# One common-support repair for the blind joint fit

One bounded repair returned both dense DS30-0008 fixes. Error fell from **1.639 / 1.512 km to 1.112 / 1.070 km** relative to v3. The candidate completed the 179-point grid with zero objective replay error and used **45.366 CPU seconds versus 59.087** for the fresh matched v3 control. Both southern decisions reproduced the unmodified candidate. The repair passed the three-case accuracy screen and missed the 24-second dense solver budget by 21.366 CPU seconds. [Prespecified repair](blind-joint-repair-protocol.md) · [Numeric summary](measurements/blind-joint-repair-summary.json) · [Full receipts](measurements/blind-joint-repair.json.gz)

## What the repair changed

The original blind joint attempt again nominated 3,643 curved and 949 predictive points and reached the same rejected diagnostic endpoints. The repair removed the union of tracks failing either calibration arm. It also removed a predictive track whose satellite lost curved support. It removed **5 of 151 tracks**, **111 of 3,643 curved points**, and **41 of 949 predictive points**. The losses were 3.31%, 3.05% and 4.32%, respectively, below the frozen 5% caps. The common support kept both receivers, 25 curved satellite families and 3,287 conservative residual degrees of freedom. Curved and predictive rows, owners and aliases that survived were identical in both arms. [Repair implementation](blind_joint_repair.py)

The two arms began at their own previously fitted endpoints with clipped phase state and recomputed the original family weights and history means on the retained support. Both finished in two phase refreshes with every surviving track compatible and final phase changes below 0.0004 s. The terminal packet assigned 4,440 observations per arm, including 3,532 curved and 908 predictive. The full v3 packet assigned 4,472, including 3,574 curved and 898 predictive. All 4,358 jointly owned observations kept their original v3 satellites. The candidate omitted 114 original owners and introduced 82. These are measured changes from a distinct accepted solution. The previous trial reproduced all stock owners only by invoking its full fallback. [Initial joint comparison](blind-joint.md)

| Saved offer | Candidate decision, both arms | Error km `c = 0` / fitted, v3 → candidate | RF RMS Hz `c = 0` / fitted, v3 → candidate |
| --- | --- | ---: | ---: |
| DS30-0008 | Returned after one repair | 1.639 / 1.512 → 1.112 / 1.070 | 129.703 / 129.663 → 128.836 / 128.761 |
| South containing | Returned without repair | 0.817 / 1.101 → 0.296 / 0.607 | 6.502 / 6.392 → 6.470 / 6.373 |
| South omitted | Withheld without repair | — | — |

The repaired dense endpoint moved farther from truth than the rejected 0.634 / 0.614 km diagnostic, and the accepted improvements over v3 were 0.527 and 0.442 km. Its RF RMS fell by 0.868 and 0.902 Hz versus v3 over changed support. On the common repaired support, learning `c` lowered RMS by 0.074 Hz and lowered error by 0.042 km. On the southern containing support it lowered RMS by 0.096 Hz and increased error by 0.311 km. The omitted branch still had two RF-compatible provisional positions with 53.948 km error before the stock exterior check withheld. Both calibration decisions are recorded separately. [Scored arms](measurements/blind-joint-repair-summary.json)

## Measured cost and the 24-second target

| Saved offer | Candidate CPU / elapsed s | Fresh matched v3 CPU / elapsed s | Fallback CPU s |
| --- | ---: | ---: | ---: |
| DS30-0008 | 45.366 / 45.538 | 59.087 / 59.105 | 0 |
| South containing | 4.046 / 4.047 | 5.245 / 5.251 | 0 |
| South omitted | 6.914 / 6.915 | 6.536 / 6.538 | 0 |

The dense candidate spent 3.894 CPU seconds preparing inputs, 16.379 in cold discovery and branch fitting, 4.134 at its first curved gate, 6.767 in salvage, 4.210 rechecking curves and nominating predictive points, and 0.667 in its first joint fit. Repair preparation took 1.830 seconds and its paired refit took 0.871. The original accepted numerical evidence cost 6.612 seconds. The candidate ran first in this saved-input pair. Relative to the fresh control it saved 23.2% CPU and 23.0% elapsed. Relative to the earlier 54.720-second exact v3 control it saved 17.1% CPU. No raw timing or new I/Q was measured.

The 24-second target requires removing 21.366 seconds from the measured accepted route. Even with free repair and free numerical evidence the rest costs 36.052 CPU seconds. Even making all cold discovery and branch fitting free with everything else at its measured time leaves 28.987 seconds. Those counterfactual costs isolate the remaining bottleneck from the successful position and RF checks. One roof and one simulated site do not establish the release's no-worse site median/P90 or omission-coverage gates. [Complete stage clocks](measurements/blind-joint-repair-summary.json)

## Reproduce

Use the same pinned installed-v3 saved-input runner and scorer as the original blind joint trial. Add `--repair` to each runner invocation, use fresh paths, and run DS30-0008 before the southern containing and omitted cases. Thirteen targeted tests passed, including the common mask, exact rejection limits, predictive curved support and unchanged fit bounds. [Reproduction commands](blind-joint.md#reproduction) · [Paired tests](../../../tests/pipeline_eval/test_algo08v3_blind_joint_repair.py)
