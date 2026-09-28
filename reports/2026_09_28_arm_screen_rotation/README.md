# Screen-only rotation experiment

`PERFORMANCE_REPORT.md` contains the measured ARM timings, exact window and
hit counts, and limitations. The host v1 and ARM v1 source snapshots and
receipts are archived in `builds/`.

Build with `.venv/bin/python reports/2026_09_28_arm_screen_rotation/build.py
--output UNIQUE` (add `--arm` or `--sanitize` as needed). The build recipe
reuses the sealed CZT builder and the qualified host-CZT source snapshot.

Validation completed: host normal and ASAN/UBSAN numerical/integration tests;
ARM all-rate integration tests; host 64 and 704 dwell cohorts; four repeated
2.5 MS/s ARM probes; four complete 2.5 MS/s ARM dwells; and 16 all-rate ARM
probes. Paired candidate checks all pass. The original-baseline summary keeps
the pre-existing negative-window mismatch and the raw original-oracle ARM
failure flags intact.

The source change is confined to the approximate regular-grid screen. No
production pipeline or scientific fixture was edited. This experiment does
not include the separately evaluated coarse FFT integration.
