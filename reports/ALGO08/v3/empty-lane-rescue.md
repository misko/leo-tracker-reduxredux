# Can the receiver predict which empty short searches deserve a retry?

Two observations available during acquisition identified most of the full-window positives that the 8 ms receiver missed. Together they triggered too many full searches to meet the predeclared cost criterion on DS30-0407. On the development recording they also missed nine of the 44 empty lanes on which ALGO08v3 had assigned a satellite. [Frozen rule and thresholds](empty-lane-rescue-protocol.md)

| Recording | Short searches returning empty | Selected for retry | Installed positives among empties | Positives covered by schedule | Estimated extra full callback wall / CPU |
|---|---:|---:|---:|---:|---:|
| DS30-0049 · development | 1,105 | 532 (48.1%) | 104 | 89 (85.6%) | 2.02 / 1.91 s |
| DS30-0407 · transfer | 6,319 | 3,420 (54.1%) | 682 | 569 (83.4%) | 13.77 / 12.98 s |

The schedule triggers on an empty short search if either the other radio on the current visit or the same radio on the immediately preceding admitted visit in the same RF stream found a signal. The positive fraction among selected lanes was 16.7% and 16.6%. Even an exact reproduction of the installed selection on the triggered lanes would cover just **35/44 (79.5%)** of the missing installed owners in both calibration arms on DS30-0049, below the 80% research threshold. The DS30-0407 owner map was outside the registered owner comparison. Its 83.4% figure measures positive detector selections. Each case used the original supplied region. The retry decisions depend only on receiver data at or before the current visit.

| Trigger observed on empty short lane | 0049 positives / opportunities | 0407 positives / opportunities |
|---|---:|---:|
| Current peer radio only | 60 / 294 | 276 / 1,268 |
| Previous same-stream visit only | 10 / 173 | 112 / 1,607 |
| Both | 19 / 65 | 181 / 545 |
| Neither | 15 / 573 | 113 / 2,899 |

The additional cost uses each recording's measured mean full-anchor callback. Retrying every empty lane at that same rate would cost 4.20 s and 25.45 s of callback wall time. If the rest of the pipeline retained its measured cost, the selected retries would leave the candidate 6.28 s and 25.13 s over the corresponding half-time budgets. This calculation assumes a local retry can read the remaining samples without extra cost. It excludes downstream changes following a new detection. The paired end-to-end speed and position results continue to come from the original field runs.

The candidate schedules for both recordings were sealed before the installed reference packets were opened. Each opportunity was paired against its original session, radio, sample clock, RF, visit identity and admission. The schedule seal is `8f124b06240c2223a94cd304fc7ddbb37649a5bbb978dba47653260a09ef7438`. The readout used saved packets and recorded timers. It launched no raw receiver or position solver. [Machine-readable counts and clocks](measurements/empty-lane-rescue.json) · [Reproducer](empty_lane_rescue.py) · [Component tests](../../../tests/pipeline_eval/test_empty_lane_rescue.py)
