# Independent final review — DS1

Reviewed after inference and evaluation seals existed; no fit, score, cache, or
reference-evaluation command was rerun for this review.

## Scope and checked bindings

The reviewed frozen dataset digest is
`sha256:9ca01caa544babf0c427871daeb08fb2b5a06598bae58e84002980c6742f715d`.
The sealed inference index is
`sha256:6f1ffa01f191efffe4017b851d8acb9132dd8e5d684faf9e52437436b3478799`;
the sealed evaluation is
`sha256:ff8aed89351f3c12a3d3ff5ce29be335c728a8ab5b53c257f8b32242c074b9b5`.

I reviewed the executed scorer
`run.py` (`sha256:9f5e96c22f849e6bab4e28c87a489f18ac1fed5a2ee3f88923ce77a9c0a433b2`),
the evaluator
`evaluate.py` (`sha256:bc394459b7d26849cb8ea274b0bfc314305b8cae53492c91af74638ec1e95c5d`),
and renderer
`render.py` (`sha256:50b71e2d19f0e7d8180026bb351a0d6d55a622260a3f0b1430591e8733ca15b0`).
Every one of the 40 inference-arm files matched its sidecar SHA-256 seal.

## Confirmed invariants

- The index has exactly 40 case/prior arms. The evaluator has exactly 80 model
  rows: 76 completed and four `input_failure` rows.
- The only failed arms are both priors of `test_20260922_00_all`; their two
  model rows each preserve the frozen position-48 session
  `scan-hop-6cd2560365a058bc` counter-continuity authority failure. No scan
  was dropped or substituted.
- The evaluator validates inference source, protocol, dataset, runner, clock
  engine, search-engine, per-session cache/receipt bindings, deterministic
  TRAIN-only winner ordering, and a fixed-winner training replay before it
  introduces the reference coordinate.
- Held observations are evaluated only after the sealed TRAIN winner is fixed.
  The capped held statistic includes every retained track and its
  occupied-second denominator; the uncapped held RMS is explicitly restricted
  to supported assignments and reports its separate supported denominator.
- The result table and both plots match the sealed evaluation rows, including
  the all-64 input failures. The 300-m marker is contextual; no DS1 completed
  row is below it.

## Outcome check and limits

The rendered and tabulated summaries reproduce the sealed outcomes: TRAIN
16/16 paired position and held improvements; validation 14/16 position and
15/16 held improvements; exposed TEST 5/6 for each. Median reference errors
are 9.138 to 4.075 km (TRAIN), 5.982 to 3.972 km (validation), and 9.419 to
8.265 km (exposed TEST). These are correlated nested views on a retrospective
regression cohort, not independent samples or untouched final-test evidence.

The shared time is an uncalibrated bounded sensitivity parameter, candidate
identities are reselected at each time/position score, and the local adaptive
geographic/time coverage is not a global-optimum or uncertainty certificate.
The review found no actionable defect in the sealed accounting, metrics, plots,
or the stated limits.

## Verification

```
.venv/bin/python -m pytest -q \
  reports/2026_09_24_ds1/test_ds1_audit.py \
  reports/2026_09_24_ds1/test_review.py \
  reports/2026_09_24_ds1/test_evaluation.py
.venv/bin/ruff check reports/2026_09_24_ds1/run.py \
  reports/2026_09_24_ds1/evaluate.py \
  reports/2026_09_24_ds1/render.py \
  reports/2026_09_24_ds1/test_review.py \
  reports/2026_09_24_ds1/test_evaluation.py
```

This review ran 16 tests and Ruff cleanly.
