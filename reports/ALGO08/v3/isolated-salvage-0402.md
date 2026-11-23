# Isolated salvage and endpoint repair restore the full named DS30-0402 roster

The combined causal route restored **all 141 missing observations in both calibration arms** and reproduced all **4,821 ordered observation, NORAD and role rows** from named v3. The saved publication took **24.082 s** through exit. The separately measured endpoint-only route took **24.384 s** and restored 61 rows. Adding isolated salvage lowered horizontal error by **55.6 / 56.0 m** relative to that endpoint-only route. Combined fixes remain **20.2 / 19.2 m** worse in horizontal error than named v3. This recording supplied the earlier loss diagnosis and is a development case. [Frozen protocol](isolated-salvage-0402-protocol.md) · [Sealed receipts and owner comparisons](measurements/isolated-salvage-0402.json.gz)

| Saved route | Through-exit elapsed | Horizontal error, fixed zero / fitted c | RF RMS, fixed zero / fitted c | Ordered owners per arm |
| --- | ---: | ---: | ---: | ---: |
| Archived named v3 | 73.351 s | 0.864 / 0.860 km | 100.672 / 100.576 Hz | 4,821 |
| Archived cumulative | 23.749 s | 0.954 / 0.949 km | 100.927 / 100.855 Hz | 4,680 |
| Endpoint-only | 24.384 s | 0.939 / 0.936 km | 100.558 / 100.496 Hz | 4,741 |
| Isolated salvage plus endpoint | 24.082 s | 0.884 / 0.879 km | 100.675 / 100.579 Hz | 4,821 |

Relative to endpoint-only, all 4,741 incumbent rows retained their family and role. The new rows were exactly the 48 named curved observations and 32 named predictive observations of NORAD 62735. The 61 conditional observations of NORAD 58377 remained associated. There were no other additions, drops or reassignments. Combined RF RMS increased by 0.117 / 0.083 Hz relative to endpoint-only, on its expanded curved support. [Sealed endpoint-only result](/dev/shm/leo-v3-endpoint-trim-0402-score01.json) · [Earlier crossed diagnosis](fragment-cross-0402.md)

## Causal admission and paired evidence

The solver found 14 original independent salvages. Nine kept the same original family and signed alias on a complete independently nominated contiguous support. One uniquely failed both the original profiled and conditional slope screens alone. The isolated fit retained the 4,103 genuine survivors and those 48 observations, removed 364 unrelated observations from the provisional calibration and restored the original assignments of the rejected proposals. One bounded fixed-zero fit on this same roster improved the normalized objective from 42,595.2649 to 42,595.1652. It reduced the target slope statistic from **3.590 to 2.239**, below the original cutoff of 3. Its original signed alias was +1. [Implementation](isolated_salvage.py)

The ensuing ordinary predictive search admitted two real alias-zero tracks of 17 and 15 observations for the newly available family. One original survivor had the only step failure in the provisional fixed-zero check and remained marked failed during prediction nomination. Both actual paired arms found that same failed curved fragment. Their original first endpoint trims left step statistics **4.096 / 4.092**. Trimming the other endpoint produced **2.878 / 2.874**, both below 4, and passed the original conditional, profile, alias, curvature and visibility checks. The shared endpoint route refit each original arm once and retained 4,150 conditional and 671 predictive observations. The signed-history update qualified and passed the original paired gates. The standard regional procedure and numerical objective replay completed. There was no broad track-deletion or full named fallback.

The runtime decision consumed only the independently nominated current observations and current fitted gates. Neither named ownership nor evaluation coordinates entered inference. Post-exit scoring used the exact observation IDs and authoritative reference. Agreement on this case does not establish transfer or uniqueness of this rule on independent recordings.

## Cost, artifacts and reproduction

| Combined saved scope | CPU |
| --- | ---: |
| Isolated test and bounded fixed-zero fit | 0.268 s |
| Predictive search, original paired fit and shared endpoint repair | 1.017 s |
| Shared endpoint repair within that paired scope | 0.282 s |
| Full numerical solve | 20.791 s |
| Standard rendering | 1.429 s |
| Whole process through exit | 24.060 s |

The single process exited zero, with zero filesystem input blocks and major faults. It used the same original signed 20 ms packet, region, causal archive and layout as the endpoint-only trial, on CPU 2 under the shared low-priority lock with one numerical thread. Those were separate launches, so the 0.302 s elapsed difference does not establish an incremental speedup. The complete earlier named and cumulative comparators also had different I/O counts. No waveform or additional full solver publication ran in this experiment.

Both numerical sidecars bind the candidate's actual position PNG. The candidate evaluated all **179** grid points with zero objective replay discrepancy in either arm. All eight standard PNGs were decoded and bound to their file digests. Their encoded and pixel digests differ from endpoint-only, and four orbit sheets changed dimensions with the original layout. The independent legend check matched all 24 fitted satellite labels and the unassociated label in the required orbit sheets, with a minimum 26 px gap.

Use `isolated_salvage_0402_trial.py launch NEW_TMPFS_ROOT`, followed by `evaluate NEW_TMPFS_ROOT RECEIPT`, with the pinned installed named interpreter and low-priority CPU 2 wrapper. The driver preserves the exact endpoint module and seals its child clock before evaluating existing comparators. Twenty focused and adjacent tests passed, including unchanged gate thresholds, causal phase and alias binding, ambiguous nomination rollback, isolated reconstruction and the one shared endpoint attempt. [Driver](isolated_salvage_0402_trial.py) · [Component tests](../../../tests/pipeline_eval/test_isolated_salvage.py)
