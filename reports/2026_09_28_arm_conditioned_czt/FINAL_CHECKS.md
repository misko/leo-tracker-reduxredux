# Final validation

- SOL implemented and tested the report-local CZT screen. Terra independently
  reviewed the algebra, integration coverage, and 704-dwell recovery counts.
- Root reproduced the original-baseline summary with
  `../2026_09_28_arm_full_optimization/independent_summary.py`, saved as
  `independent-summary.json`.
- Root independently compared every complete candidate object to the preceding
  scoped host run: 123,904 objects in 15,488 windows, all identical. Input hashes,
  row keys, receiver/probe keys, and native return codes were checked. See
  `root-paired-verification.json`.
- `compare_arm_cohort.py` verifies all 704 candidate objects in 88 ARM windows
  against the preceding ARM run. Full ARM cohort harness passed its baseline
  audit and recovered all 119 hits and 49 positive windows.
- The sealed previous report's `compare_probes.py` verifies all candidate
  objects and coarse-grid bytes for four repeated 2.5 MS/s probes and 16
  all-rate probes. Both comparisons pass. Raw original-oracle probe receipts
  remain `passed: false` because of inherited coarse FP32 differences.
- Host normal and ASAN/UBSAN numerical/integration tests pass; their exact
  sources, outputs, and build commands are archived under `builds/`.
- ARM numerical unit test passes, with its executable hash and output retained
  under `arm-unit-v3/`. The expanded later host tests changed no main source
  file from the qualified host v2 / ARM v3 implementation.
- Qualified source and executable hashes were verified against build receipts.
  Source archives and the ARM float FFTW static-library hash are retained.
- No production code was changed by this experiment. No RF collection was
  started. ARM benchmark processes finished; no benchmark job remains running.

The sample does not establish universal equivalence or simultaneous-capture
readiness. The 40%-headroom goal remains unmet. `SHA256SUMS.json` covers this
report directory excluding itself and Python bytecode caches.
