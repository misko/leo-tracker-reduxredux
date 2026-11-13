# Bounded algo07v5 accuracy–speed investigation

Status: **incomplete**. Two fresh pairs, all three DS29-0399 pairs and the
single weak-track attempt are terminal. Three DS26-0002 control pairs remain
in progress. Final direct-gap recommendation waits for all eight pairs,
including failures and timeouts.

The frozen scope, source/native bindings and exact launch command are in
[the evaluation guide](initial-discovery-evaluation.md#direct-timing-gap-follow-up).
This comparison adds `direct-timing-gap-v1` to fast-v5-zero. It does not measure
speedup against original v3. Both roles use CPU 21, one BLAS thread, matched
inputs and budgets, null inference GPS, and the same frozen scientific source.
DS29 errors use operator roof references, not independently surveyed truth.

## Terminal fresh pairs

| Case | Arm | Baseline → candidate error, m | Frequency score | RMS, Hz | Exact ownership change |
| --- | --- | ---: | ---: | ---: | --- |
| DS26-0263 | c0 | 788.223 → 788.223 | 35800.547 → same | 240.606 → same | None; 3384 owners |
| DS26-0263 | fitted c | 796.515 → 796.515 | 35791.928 → same | 216.267 → same | None; 3384 owners |
| DS29-0126 | c0 | 629.528 → 629.528 | 12922.526 → same | 113.643 → same | None; 1529 owners |
| DS29-0126 | fitted c | 429.243 → 429.243 | 12925.613 → same | 90.583 → same | None; 1529 owners |

| Case | Wall, s | CPU, s | Gap stage, s | Native calls | Native fallbacks |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS26-0263 | 467.150 → 498.995 | 462.384 → 494.668 | 0.0046 → 60.3679 | 4734 → 6239 | 0 → 0 |
| DS29-0126 | 160.199 → 165.732 | 158.205 → 162.308 | 0.0017 → 0.0018 | 2637 → 2637 | 0 → 0 |

All four workers completed with exit zero. DS26-0263 independently nominated
NORAD 67408 for a 41-point component, but the paired RF gates and exact-replay
verification rejected inclusion. Its audit ran and returned failed verification;
the generic persisted reason `exact replay fails or missing` does not mean the
audit was absent. Direct annotation, inclusion and audit consumed 34.951,
24.163 and 1.234 seconds, respectively, within the 60.368-second gap stage.
DS29-0126 found no qualifying timing component and performed no direct fits.
Both cases preserve exact scientific outputs between roles. Timing differences
in these single contended pairs do not establish repeatable overhead.

The worker owner revalidated public stores, report/request/work receipts,
source/native/provider bindings and archive hashes without numerical reruns.
Evidence is under
`/srv/bulk/leo-dev/initial-discovery-20261113/direct-gap-followup-001/`:

- `audit-ds26-0263/pair-audit.json`, SHA256
  `3f122af840baa4a432f4a721d760cf5eb79d710aafb973c1dc4e03dd876d1772`.
- `audit-ds29-0126/pair-audit.json`, SHA256
  `b456970d88b01f73f7011a5871ef8498f7a64d2fa8f60b146c8552fad1732bdf`.

## DS29-0399 alternating repetitions

All six workers completed with exit zero. Independent review verified actual
execution order baseline/candidate, candidate/baseline, baseline/candidate,
the public audits, exact owner sets and frozen source/native/provider bindings.
Every role's complete scientific arm dictionaries exactly match its other two
repetitions and the prior development screen. This establishes reproducibility
on one development recording, not independent holdout generalization.

| Arm | Baseline → candidate error, m | Frequency score | RMS, Hz |
| --- | ---: | ---: | ---: |
| c0 | 1269.409 → 377.472 | 16092.020 → 16774.805 | 101.208 → 104.963 |
| fitted c | 1311.255 → 466.076 | 16096.445 → 16776.683 | 78.991 → 87.722 |

Each candidate adds exactly the same 56 target observations as NORAD 66466 in
both arms, retaining all 2010 incumbents unchanged and reaching 2066 owners.
Each physical audit verifies and the production qualification passes. Frequency
scores and RMS above cover different observation sets between roles; they do
not establish a matched-observation frequency improvement. Position accuracy
comes from the separately held evaluation reference.

| Repetition | Order | Baseline wall, s | Candidate wall, s | Baseline CPU, s | Candidate CPU, s |
| --- | --- | ---: | ---: | ---: | ---: |
| 0 | B/C | 346.378 | 407.117 | 342.750 | 402.952 |
| 1 | C/B | 352.475 | 387.787 | 348.775 | 384.304 |
| 2 | B/C | 333.496 | 396.490 | 330.496 | 393.453 |

Candidate/baseline wall ratios are 1.17535, 1.10018 and 1.18889, with aggregate
1191.394 / 1032.349 = 1.15406. CPU aggregate is 1180.708 / 1022.021 = 1.15527.
Paired wall overhead ranges 35.313–62.994 s, median 60.738 s; CPU overhead
ranges 35.529–62.957 s, median 60.201 s. These are contended host observations,
not a general latency estimate. Each pair uses 6506 → 8380 native calls,
20 receipts per role, and zero fallbacks. Per-pair audit receipts are under
`direct-gap-followup-001/audit-ds29-0399-r{0,1,2}/` in the experiment root.

## Weak-track inclusion decision

**Stop this lever for now.** The one bounded DS26-0102 attempt completed its
primary fit and physical audit but failed the c0 optimizer acceptance gate.
Its permitted Powell retry timed out at 110.003 seconds. No inclusion was
accepted. The unaccepted primary proposal added 33 points without losing
incumbents, but worsened reference error by 12.323 m for c0 and 20.763 m for
fitted c; actual accepted error and ownership changes are zero. Frequency-fit
changes were negligible and mixed. All 1043 native calls activated without
fallback. There is insufficient demonstrated benefit to extend the retry now.

[The independently audited report](weak-track-inclusion-ds26-0102.md) contains
both-arm baseline/control/proposed endpoints and frequency metrics, stage wall
and CPU, explicit incomplete retry accounting, artifact hashes and exact CLI.
Tool/tests are committed as `5bb61e625`; 13 focused tests passed. The report and
stop decision are committed as `6305a0cca` and `f682a2dd8`.

## Remaining evidence

Three fresh pairs on no-trigger DS26-0002 must finish in baseline/candidate,
candidate/baseline, baseline/candidate order. Their terminal reports must
establish repeatability of outputs, owner changes, stage work, wall/CPU cost
and failure/fallback counts. Only then finalize the direct-gap advance/revise/
stop recommendation. No further experiment, full-cohort launch, new RF
collection or default promotion is authorized by this bounded goal.
