# Full visible-catalogue check under stationary offset profiling

All three frozen audits completed: 172 tracks and 91,353 visible track/candidate combinations. No omitted candidate had the highest training score. Two tests pass, covering posterior-mass arithmetic, frozen input hashes, all selected tracks, and result aggregation.

| Session | Tracks | Minimum retained training mass | Full-catalogue training log-score gain | Held-out log-score change |
|---|---:|---:|---:|---:|
| scan-fw-60d9d1e77c14da0a | 58 | 0.977095342 | 0.023173029 | -0.023173029 |
| scan-fw-aa9770c66396e928 | 57 | 0.989984504 | 0.010065989 | -0.010065989 |
| scan-fw-457f07dabb21e096 | 57 | 0.999998187 | 0.000002000 | -0.000001869 |

The three scans were selected by lowest anchor shortlist mass in the element-freshness baseline, before inspecting this experiment's results. Geographic error was not used for selection or fitting. Every baseline-roster satellite visible at any training epoch was propagated exactly at the corrected stationary solver's fitted location and time offset. The causal per-provider element selection and the stationary scalar offset solver match the corrected per-scan experiment. Original randomized whole-visit training/evaluation assignments are retained.

The inherited shortlists retain almost all training probability at these three fitted points. Expanding them produces very small training gains and slightly worse held-out prediction. This does not support shortlist omission at these points as the main explanation for the position errors. It does not prove completeness at other locations, global location optimality, or performance on other scans. Satellite identities remain model candidates, not decoded ground truth. Scalar optimization uses finite mode brackets, not a global-optimality proof.

No position was refitted here. The corrected independent-scan result remains 6/43 below 1 km, with mean error 3.333 km. The earlier pooled estimate below 1 km still requires revalidation with the corrected all-track solver; this audit does not establish that pooled result.

Inputs, source, and selection are frozen in protocol.json. Each result binds that protocol by SHA-256. The next step is to revalidate the joint static-site fit with the same corrected stationary offsets and the original randomized whole-scan A/B split.
