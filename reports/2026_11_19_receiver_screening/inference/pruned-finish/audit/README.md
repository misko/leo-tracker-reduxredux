# Original v5 final-stage eligibility on 135 recordings

The support check removes 890 of 2,956 original ranked orbit families and 1,780 of 5,912 per-arm leave-one-out evaluations (30.1%). A required held-time fold was unavailable for 106 of 382 residual targets (27.7%). The original residual screen would have no target requiring propagation in five recordings under the pruning rules, including two recordings with no offered target.

| Family influence and reassociation | DS26 | DS29 | Total |
| --- | ---: | ---: | ---: |
| Recordings | 127 | 8 | 135 |
| Observed families ranked by original v5 | 2,781 | 175 | 2,956 |
| Families with at least 30 retained points and two tracks | 1,955 | 111 | 2,066 |
| Original per-arm leave-one-out evaluations | 5,562 | 350 | 5,912 |
| Per-arm evaluations passing the support check | 3,910 | 222 | 4,132 |
| Support-eligible families scoring at least 0.5 before cap | 449 | 25 | 474 |
| Families selected after the two-family reassociation cap | 216 | 15 | 231 |
| Recordings where the cap cut the ranked list | 80 | 6 | 86 |
| Reassociation proposals admitted to fitting | 2 | 0 | 2 |

The final causal screen completed on all 135 recordings. It received zero families on eight recordings, one family on 23 and two families on 104. The archived ranking supplies the original first-observed support and arm membership for each family, which determines the exact number of omission calls.

| Residual additions | DS26 | DS29 | Total |
| --- | ---: | ---: | ---: |
| Eligible fragments before the three-target cap | 1,195 | 50 | 1,245 |
| Targets screened by original v5 | 361 | 21 | 382 |
| Targets with three required held folds and scores in each calibration arm | 259 | 17 | 276 |
| Targets passing the original paired screen | 55 | 5 | 60 |
| Screen winners already present among owned families | 19 | 1 | 20 |
| Eligible new-family proposals | 36 | 4 | 40 |
| Recordings with a chosen addition | 32 | 3 | 35 |
| Additions qualified / rejected | 11 / 21 | 0 / 3 | 11 / 24 |

The other 106 screened targets had zero, one or two held folds in counts of 1, 22 and 83. All 135 pre-addition incumbents used zero conditional family mixtures, so the separate two-mixture exclusion prunes zero targets here. The trial's measured paired finish controls remain the evidence for runtime and position. [Pruned finish protocol](../PROTOCOL.md)

The receipt field `residual_pruned_fit_eligible_targets` counts targets that would reach numerical screening after the held-fold and incumbent-mixture checks. The later paired screen and best-new-family selection determine which targets receive a position fit.

The audit reads the original no-repair repetition-zero scientific ZIP and execution receipt for each frozen roster ID. It checks the whole archive SHA-256, source and embedded request binding, then extracts only the recorded ranking, residual preparation, residual screen and admission decisions. It reads no RF captures, endpoint arrays or geographic truth. Each row carries its original archive, request and execution receipt hashes. The output SHA-256 is `c40d02dea128db00410eb521255899168aa68638f8b2d9c5e7d2d2b1d10930b8`. [Authenticated per-recording counts](eligibility.json)

```sh
.venv/bin/python -m tools.pipeline_eval.qualification.pruned_finish_audit \
  --jobs 2 --out /tmp/pruned-finish-eligibility.json
```
