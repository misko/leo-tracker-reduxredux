# Execution record

Run from `/home/mouse9911/gits/leo-tracker-reduxredux` on 2026-09-28 UTC.
The extraction used the installed service runtime solely for its public,
read-only storage adapter:

```bash
sudo -n nice -n 19 /opt/leo-tracker/current-api/.venv/bin/python \
  reports/2026_09_28_ds7_large_arm/prepare.py extract \
  --plan reports/2026_09_28_ds7_large_arm/plan.json \
  --output /var/tmp/leo-ds7-large-arm-20260928
```

The generated final input manifest was copied into the report directory:

```bash
cp /var/tmp/leo-ds7-large-arm-20260928/inputs.json \
  reports/2026_09_28_ds7_large_arm/inputs.json
```

The scientific baseline used this checkout's virtual environment, eight
persistent worker processes pinned individually to server cores 0 through 7,
and one requested numerical-library thread per process:

```bash
env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 FFTW_NUM_THREADS=1 nice -n 19 \
  .venv/bin/python reports/2026_09_28_ds7_large_arm/run_baseline.py \
  --inputs /var/tmp/leo-ds7-large-arm-20260928 \
  --plan reports/2026_09_28_ds7_large_arm/plan.json \
  --output reports/2026_09_28_ds7_large_arm/baseline-01
```

The completed rows were audited with:

```bash
.venv/bin/python reports/2026_09_28_ds7_large_arm/summarize_baseline.py \
  reports/2026_09_28_ds7_large_arm/baseline-01 \
  --output reports/2026_09_28_ds7_large_arm/baseline-summary.json

.venv/bin/python -m pytest -q \
  reports/2026_09_28_ds7_glrt_benchmark/test_run.py
```

The extraction read only the selected saved chunks beneath `/srv/bulk/leo`.
It performed no RF collection and no QNAP mutation. The parallel baseline is a
scientific result baseline; its elapsed time is not an ARM timing comparison.
