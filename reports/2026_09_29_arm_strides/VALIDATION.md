# Validation record

Final combined suite: **74 passed in 13.18 s** on 2026-09-29:

```bash
PYTHONPATH=src:/var/tmp/leo-strides-pinned-pluto-dependency/src python -m pytest -q \
  tests/qualification/test_arm_glrt_release.py \
  tests/analysis/test_native_glrt.py \
  tests/contracts/test_arm_glrt.py \
  tests/cli/test_arm_glrt_cli.py \
  tests/cli/test_process_cli.py \
  tests/cli/test_scanner_glrt_runtime.py \
  reports/2026_09_29_arm_strides/test_analyze.py
```

The optional CLI radio dependency came from the repository-pinned
`pluto-plus-utils` commit `cc65fe95e470e95cc06a87ae497bfec4ddc1c5e4`,
exported read-only into that temporary path. No test opens the radio. The new
standalone module CLI is separately tested without the optional radio package.
This is the targeted suite, not a claim that every repository test was run.

- Host native tests execute all 36 rate/dwell/stride combinations, shared
  scientific parity, reuse/failure behavior, and old/new library coexistence.
- ASan/UBSan/leak checking passed during extraction and namespace review.
- A built wheel contains all 28 native component files, including namespace
  wrappers; building the host CLI from the unpacked wheel succeeded.
- All 336 real saved-dwell ARM executions completed and validated through the
  maintained output port. Input, binary, template and output hashes are retained.
- All repeats returned identical scientific candidate values.
- Archive extraction/hash verification and regeneration reproduced all aggregate
  and per-case comparison values. No IQ access is needed for this replay.
- Original baseline coverage: all 56 selected contexts have complete 22-window
  inventories, indexed by authoritative probe start rather than ordinal.
- Physical synthetic qualification passed 33/36 mode combinations under a
  220,000 KiB virtual-memory limit. 10 MS/s × 360 ms is not memory-qualified.
  Its allocation failures and the earlier unbounded OOM kill are preserved,
  not silently skipped or described as passing.
- New source/tests and report analysis/archive/render lint checks passed;
  `git diff --check` passed. The exact executed benchmark runner is preserved
  unchanged because its SHA is bound in the execution manifest.
- PNG visualizations were inspected. SVG and HTML companions are included.

The measured build receipt is preserved byte-for-byte. A documentation-current
rebuild produced the identical executable SHA. GCC7 LTO archive bytes differed;
the report does not claim archive bit reproducibility. No historical PGO data
was reused and no host timing was placed in an ARM timing column.
