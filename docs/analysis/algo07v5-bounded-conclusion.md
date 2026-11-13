# Bounded algo07v5 accuracy–speed investigation

Status: **incomplete**. Two fresh pairs and the single weak-track attempt are
terminal; six alternating repetition pairs remain in progress. Final direct-gap
recommendation waits for all eight pairs, including failures and timeouts.

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

Three fresh pairs each on DS29-0399 and no-trigger DS26-0002 must finish in
baseline/candidate, candidate/baseline, baseline/candidate order. Their terminal
reports must establish repeatability of outputs, owner changes, stage work,
wall/CPU cost and failure/fallback counts. Only then finalize the direct-gap
advance/revise/stop recommendation. No further experiment, full-cohort launch,
new RF collection or default promotion is authorized by this bounded goal.
