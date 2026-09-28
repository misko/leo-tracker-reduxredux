# Execution and reproduction

The frozen selection is in `plan.json`; the extracted input receipts are in
`inputs.json`. IQ lives in `/var/tmp/leo-arm-ds89-validation/inputs` and is read
from the original store through its public read-only adapter. The plan uses a
legacy DS7 runner schema solely to reuse that immutable research harness;
every context retains its actual `dataset_id` of DS8 or DS9.

Extraction:

```sh
sudo -n nice -n 19 /opt/leo-tracker/current-api/.venv/bin/python \
  reports/2026_09_28_arm_ds89_validation/prepare.py extract \
  --plan reports/2026_09_28_arm_ds89_validation/plan.json \
  --output /var/tmp/leo-arm-ds89-validation/inputs
```

Original scientific baseline:

```sh
env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 FFTW_NUM_THREADS=1 nice -n 19 \
  .venv/bin/python reports/2026_09_28_ds7_large_arm/run_baseline.py \
  --inputs /var/tmp/leo-arm-ds89-validation/inputs \
  --plan reports/2026_09_28_arm_ds89_validation/plan.json \
  --output reports/2026_09_28_arm_ds89_validation/baseline-v1
```

Frozen candidate:

```sh
nice -n 19 .venv/bin/python reports/2026_09_28_arm_ds89_validation/run_candidate.py \
  --inputs /var/tmp/leo-arm-ds89-validation/inputs \
  --baseline reports/2026_09_28_arm_ds89_validation/baseline-v1/rows.jsonl \
  --output reports/2026_09_28_arm_ds89_validation/host-boundary-v1 --workers 8
```

Require the original run receipt to report complete, unchanged sources, zero
failures and 680 calls. The candidate's inherited `complete` field only means
the runner finished; successful strict inventory loading by the frozen scorer
is required. Its ordered-field equality audit intentionally fails for an
approximate method; that is separate from individual-hit recovery.

```sh
.venv/bin/python reports/2026_09_28_arm_boundary_fallback/score.py \
  --cohort reports/2026_09_28_arm_ds89_validation/host-boundary-v1 \
  --baseline reports/2026_09_28_arm_ds89_validation/baseline-v1/rows.jsonl \
  --output reports/2026_09_28_arm_ds89_validation/host-hit-audit.json
.venv/bin/python reports/2026_09_28_arm_ds89_validation/summary.py \
  --host reports/2026_09_28_arm_ds89_validation/host-boundary-v1 \
  --baseline reports/2026_09_28_arm_ds89_validation/baseline-v1/rows.jsonl \
  --output reports/2026_09_28_arm_ds89_validation/host-summary.json
```

`arm-selection.json` freezes eight input identities and hashes before ARM work.
The same original detector was replayed separately on those eight inputs using
`arm-baseline-plan.json` and `arm-inputs.json`, allowing serial ARM work to
overlap the large host baseline. ARM execution order is DS8 boundary, DS8
exact-cache, DS9 exact-cache, DS9 boundary. Each run uses `run_arm.py` with
`--dataset DS8|DS9 --method boundary|exact-cache`, the full input directory,
and `--baseline .../arm-baseline-v1/rows.jsonl`. All ARM operations are serial
on the device. Scoring uses the maximum-cardinality matcher, not the inherited
timing harness's greedy diagnostic matcher. The subset baseline must agree
with the corresponding completed large-baseline results before final reporting.

These are saved-file experiments: no RF collection, no simultaneous capture,
no changes to production analyzers, no modification of DS7/DS8/DS9 snapshots.

The first DS8 ARM attempt (`arm-ds8-boundary-v1`) stopped during the all-rate
unit test because the reused transport allowed only 30 seconds. No dwell was
benchmarked in that attempt. After confirming no remote process remained, the
wrapper was given the existing standalone ARM unit harness's 120-second unit
allowance. Subsequent ARM runs use `v2` folders; algorithm binaries are unchanged.
