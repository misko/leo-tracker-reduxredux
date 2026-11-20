# Can causal TLE history predict signed orbital timing error?

The signed forecast got the direction right for **64.2% of 1,795 strong later revisions with a nonzero forecast**. Its magnitude was unreliable on the held catalogue dates. It raised RMS timing error from 5.350 to 5.946 s and mean absolute error from 1.843 to 2.204 s. The proxy result failed the predeclared criterion of at least 5% RMS reduction and improvement on at least four of six dates. In the separate blind receiver test, the signed mean recovered one publication and lost three. The zero-centered default had higher coverage. [Catalogue scores](catalogue-scores.json) · [Blind position scores](scores.csv)

## Signed forecast and site-free proxy

Positive orbital phase advances the current TLE’s satellite position along its TEME velocity. At the target UTC, project `current_position − previous_position` onto the current velocity and divide by squared speed to get the prior-to-current timing innovation in seconds. The forecast continues that sign, uses one-half shrinkage, and multiplies by current element age divided by the previous-to-current epoch gap, capped at two. It tapers short gaps and falls back to zero for unavailable, stale or transverse-dominated history. The mean is limited to ±15 s. This is a fixed physical rule. The original frozen v5 implementation also forecast signed phase with a data-selected coefficient on past transitions. The previous lean phase-support experiment used disagreement for width and did not use its sign. [Locked protocol](PROTOCOL.md) · [Forecast and input rules](../../../../tools/pipeline_eval/variants/phase_forecast.py)

The catalogue holdout requested six fixed 12:15 UTC epochs and six disjoint salted groups of 512 NORADs. Past catalogue bytes were selected using recorded retrieval times and verified by digest. The latest eligible earlier element came from a strictly earlier collection. A proxy was the first later collection within 48 hours with a same-satellite element whose epoch was after the five-minute target interval. It was propagated back to the original target UTC before taking the signed difference. This proxy uses the same Space-Track provider and supplies no independently measured orbital truth. Seven of the 3,072 attempts lacked a proxy. No radio data or site estimates entered this test. [Source ledger](catalogue-inputs.json) · [Per-satellite pairs and hashes](catalogue-pairs.jsonl.gz) · [Catalogue seal](catalogue-lock.json)

| Held date | Matched proxies | Zero mean RMS | Signed forecast RMS |
| --- | ---: | ---: | ---: |
| 2026-10-16 | 511 | 3.142 s | 3.807 s |
| 2026-10-22 | 512 | 2.894 s | 2.647 s |
| 2026-10-28 | 512 | 8.673 s | 10.205 s |
| 2026-11-03 | 510 | 5.676 s | 5.673 s |
| 2026-11-09 | 510 | 5.623 s | 6.404 s |
| 2026-11-15 | 510 | 3.789 s | 3.633 s |
| All | 3,065 | 5.350 s | 5.946 s |

The opposite-sign placebo also worsened pooled RMS to 6.392 s. The signed rule’s median absolute error rose from 0.721 to 0.778 s and its pooled forecast–proxy correlation was 0.045. Its sign advantage on active, strong proxies does not carry over to an accurate fixed prior mean. [Forecast figure](catalogue-forecast-skill.png)

## Blind downstream consequence

The same sealed signed rule entered the anonymous native joint receiver after the catalogue score was finalized. The worker consumed complete archived GLRT, the original causal catalogue and authenticated past snapshots, and the existing local tile offer. It shifted each orbit’s phase origin before shortlisting, assignment, exact joint refinement, and held publication. The orbit-relative phase width and ±7.5 s residual search stayed fixed. Total phase support could extend beyond ±7.5 s around zero. Both calibration arms shared the phase priors and assignment procedure. The worker had no published v5 ownership or phase, GNSS, or retrospective element. [Native scope, sources and requests](native-plan.json) · [Predictions](prediction-lock.json) · [Both-arm standard figures](figures.json)

| Cohort | Nominal published | Signed published |
| --- | ---: | ---: |
| Two diagnosed recordings | 0/2 | 1/2 |
| Four salted reserve recordings | 4/4 | 1/4 |
| Both matched groups | 4/6 | 2/6 |
| Two authentic omitted offers | 0/2 | 0/2 |

Counts are the same in both c arms. DS26-0197 published at 0.788/0.383 km error versus nominal forced 1.884/1.189 km. This does not establish recovery of its disputed family. The physical forecast assigned 67348 a prior of −8.842 s, opposite the archived v5 diagnostic phase of about +14.3 s, and neither new arm retained this satellite. For DS26-0223 the −4.439 s mean led to a genuine 67315 assignment of four curved tracks and all 184 points at fitted physical phases −10.293/−10.316 s. The fit still withheld. Forced position error increased from 1.635/1.832 to 5.001/4.946 km and RF RMS increased from 191/179 to 200/190 Hz. [Full phase and owner traces](phase-means.jsonl.gz) · [Earlier archived owner audit](../../recovery/conditional-support/README.md)

The reserve row that still published was DS26-0237. DS26-0098, DS29-0082 and DS29-0247 lost publication, although DS29-0082’s forced error and RF residual both improved. The two omitted requests used authentic archived wrong tiles. Both methods withheld on both of them with actual forced estimates retained in the score. The initial catalogue study took 7.9 s and the eight native jobs took 28.4 s on two CPUs. Median complete native worker CPU was 5.30 s versus 4.71 s on the separately scheduled nominal archive. The phase setup took a median 0.73 s wall including the new orbit bank and history I/O. Candidate peak RSS ranged from 139 to 147 MiB. The bench starts from complete stored GLRT, before Graph reconstruction. [Matched control positions](control-positions.jsonl.gz) · [Score breakdown](scores.json)
