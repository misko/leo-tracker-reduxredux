# Reproducing this bounded research comparison

Use the existing scientific environment and the pinned deployed analysis source.
This directory contains orchestration and experimental methods; it does not
modify installed analysis code or any deployed worker.

From the repository root:

```bash
sudo -n env PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH=/opt/leo-fast-auto/f141dbb30321bc8f9e8183576c511431ea60a6b3/worker/src \
  OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  /opt/leo-tracker/releases/47e2705e437722daa5e6d6bb1c252d54b7a21dbc/.venv/bin/python \
  reports/2026_10_16_dsx01_models/run_evaluation.py \
  --modes full early_to_late late_to_early --workers 8
```

The default matrix has 125 results: five immutable originals, 40 full-data
variants/continuations, and 80 candidate-conditioned temporal variants. Every
new fit has a cap of 180 objective/proposal evaluations and 120 wall seconds.
The implementation reports orbit-profile projections separately. Existing
result files are not overwritten or retried. For a fresh repeat, supply a new
`--output` directory; do not silently mix results from changed algorithms.
The summary and validator read the original `results` directory deliberately.

Each receipt records source input and terminal digests, ordered satellite timing
outputs, complete endpoint arrays, inference costs, independent common-domain
audit, and metrics on all/challenge/outside populations. Three first S03 replay
receipts predate addition of the code-hash field; the final artifact manifest
binds their files and the unchanged numerical code. All subsequent receipts
carry source-code hashes too. Original production acceptance and common-domain
research KKT acceptance have different search constraints, as explained in the
report.

The temporal arms rebuild zero band contrasts and neutral parameter seeds,
without using full-recording position/calibration/timing or held CFO to fit.
Their bank comes from saved full-recording discovery, so validation is explicitly
conditional on that bank. The held-half assignment still uses the same measured
CFO versus predicted mixture rule at scoring time; it is not verified identity
accuracy.

Run component tests using the same environment and interpreter:

```bash
python -m pytest reports/2026_10_16_dsx01_models/test_common.py \
  reports/2026_10_16_dsx01_models/test_model_a.py \
  reports/2026_10_16_dsx01_models/test_model_b.py \
  reports/2026_10_16_dsx01_models/test_model_c.py -q -p no:cacheprovider
python reports/2026_10_16_dsx01_models/validate_results.py
python reports/2026_10_16_dsx01_models/summarize.py
```

Here `python` means that pinned interpreter with the environment above. Tests
require no hardware, QNAP or PostgreSQL. Replay/evaluation uses existing local
scientific receipts through public storage adapters and requires read access to
the existing bulk and TLE archives. There is no RF collection or production write.
