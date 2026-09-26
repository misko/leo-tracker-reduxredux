# Reproducing the bounded replay

Execution checkout: `/srv/bulk/leo-dev/scan-32a202-phase-replay`, base `e1a24b200d4bb68d4f38484dc591e9b9616a2e70`. Report scripts and tests are uncommitted artifacts in this isolated checkout. Production code was not changed.

Source: `/srv/bulk/leo/scanner-adaptive-recordings/scan-fw-32a202b6e55630ec/manifest.json`. The canonical manifest-document SHA-256 is `b381f62da5b5490e43790b69e2947919ad9fee6441b642ac04e7af1be487993a`; this differs from hashing its enclosing file. Full integrity evidence is in `capture-audit/source-provenance.json` and `capture-audit/chunk-integrity.json`.

The frozen selection is `selection.json`; its seed is 20260926. Reusable read-only source arrays are in `/srv/bulk/leo-dev/scan-32a202-phase-replay-cache/selected-visits`; dense acquisition checkpoints are in `/srv/bulk/leo/experiments/scan-fw-32a202-phase-replay/acquisition-dense-v1`; frame folds are in `/srv/bulk/leo-dev/scan-32a202-phase-replay-cache/frame-folds`. These caches are required for recomputation and are not duplicated in the report.

Use the pinned release Python for scientific dependencies, with the replay checkout on PYTHONPATH:

```bash
cd /srv/bulk/leo-dev/scan-32a202-phase-replay
export PYTHONPATH="$PWD/src"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
export MPLCONFIGDIR="$PWD/.mplconfig-coordinator"
```

The complete runtime is `/opt/leo-tracker/releases/2c30eaf50064623a666e1c078c56a02cb3223a70/.venv/bin/python`; this host requires `sudo -n env` with the above variables to access it. The ordinary checkout venv can render reports but currently lacks scipy. Do not alter production dependencies.

Each package retains its runnable scripts and JSON/CSV evidence. Acquisition commands and configuration are recorded in `acquisition/README.md`; source selection and masks in `capture-audit/REPORT.md`; final full-span tracker output in `frame-methods/fullspan/fullspan-trackers.json`. Authoritative later passes are `dual-rx/run_dense_direct.py`, `dual-rx/run_dense_relative_phase.py`, `sync-spectral/run_guarded_spectral.py` (v5), and `frame-methods/row16-root/run.py`. Inspect each script's CLI before recomputing. Preserve the frozen selection, train/evaluation split, phase-blind candidate ranking and explicit duration exclusions.

After numerical outputs exist, run `frame-methods/row16-root/render.py`, then `build_final_report.py` from this report directory's scripts. `build_final_report.py` creates REPORT.md, method-summary.csv/json and overview.png/svg. `seal_artifacts.py` regenerates exclusions.csv and artifact-manifest.json after all edits.

Validation command: pinned runtime `-m pytest -q tests/reports --junitxml=reports/2026_09_26_scan_fw_32a202b6e55630ec_phase_replay/test-results.xml`. Final receipt: 23 passed. Raw capture, caches and earlier experimental diagnostics are never overwritten to force a passing result.

All comparisons are offline. Some expensive historical kernels use explicitly bounded development subsets. The final method ledger states actual scope for every row; it must not be read as 30 independent full-cohort validations.
