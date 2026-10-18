# Validation of this partial report snapshot

The publication freezes 497 paired completed pipeline results and regenerates figures and summary tables from those immutable compact records. It leaves the ongoing numerical campaign untouched. The [snapshot receipt](snapshot_receipt.json) distinguishes this bounded publication from a complete campaign result.

The following focused component tests passed on 2026-10-18: **42 passed in 4.75 s**.

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=src:tools .venv/bin/pytest -q \
  tests/analysis/test_dsx01_radial_restarts_tool.py \
  tests/analysis/test_dsx01_radial_adapters_tool.py \
  tests/analysis/test_dsx01_radial_restart_report_tool.py \
  tests/analysis/test_dsx01_radial_figure_comparison_tool.py \
  tests/analysis/test_dsx01_radial_restart_audit_tool.py \
  tests/analysis/test_dsx01_radial_watcher_tool.py
```

The subsequent combined run adds `tests/analysis/test_dsx01_purple_basin_tool.py` and passes **44 tests**. Ruff is clean for the three new purple-endpoint diagnostic tools. These diagnostic tests and source snapshots are included alongside the radial suite.

The [purple-endpoint receipt](purple_diagnostics/validation.json) separately verifies six endpoint replays, 18 controlled cross-start fits, 20 common-reference interventions, 64 fixed-position subset comparisons, six conditional geographic fields containing 1,080 samples, and three paired eight-round runs with 24 outer rounds. The extended first two rounds reproduce the original two-round parameters exactly. A redundant repeat of the already completed S09 extension was canceled before overwrite; canonical artifacts passed validation, and no successful combined-command exit is claimed.

All 497 included records have both finite arm endpoints and match the campaign source fingerprint. Original full worker hashes were rechecked while retaining their per-record input audit/read receipts in the compact publication. All 201 Python files covered by the source bindings match their recorded hashes. These checks are recorded in [snapshot_validation.json](snapshot_validation.json). The published original-versus-new galleries contain all 245 planned scan/configuration entries, with 43 available paired figures and explicit pending entries. Thirty-seven scan/configuration combinations include all 13 starts. No pending entry is drawn as a completed fit.

The copied live [consistency audit](consistency_audit.json) covers its recorded subset and reports no errors, but is incomplete for the planned campaign. The [earlier endpoint replay](endpoint_gradient_replay.json) covers four endpoints and reproduces their conditional objectives exactly. Neither receipt establishes complete-campaign convergence or universal satellite identity correctness.

The [manifest](publication_manifest.json) hashes the final publication bytes. [Original worker bindings](live_result_bindings.json) preserve the relation between full local results and the compact published records; [compact bindings](result_bindings.json) bind the records actually consumed to regenerate the plots. Source snapshots support review and plotting; complete numerical replay also needs local archived radio and orbital inputs.
