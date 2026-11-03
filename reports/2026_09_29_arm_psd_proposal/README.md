# PSD-guided coarse GLRT prototype

Start with [measured results](REPORT.md) and the [frozen protocol](PROTOCOL.md).
This is an experimental research runner, not a production analysis mode.

The prototype tests whether raw power-spectrum shape can choose a small subset
of the eleven original frequency hypotheses. `psd_proposal.py` contains the
Python estimator; `psd_probe.c` is its native ARM timing counterpart.
`full_search.c` and `coarse_fp32.h` implement actual masked coarse computation,
followed by the previously validated boundary-fallback GLRT. Source and binary
receipts are archived under `builds/`; `psd-builds.json` binds the separate
native spectrum estimator.

From the repository root, using new output paths because runners refuse to
overwrite completed results:

```sh
env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python \
  reports/2026_09_29_arm_psd_proposal/features.py \
  --dataset DS7 --output /var/tmp/psd-ds7-new

.venv/bin/python reports/2026_09_29_arm_psd_proposal/build.py \
  --output /var/tmp/psd-native-new

.venv/bin/python reports/2026_09_29_arm_psd_proposal/run_native.py \
  --features /var/tmp/psd-ds7-new --binary /var/tmp/psd-native-new/cohort_mask \
  --output /var/tmp/psd-sqrt5-new --method sqrt5 --workers 8

.venv/bin/python reports/2026_09_28_arm_boundary_fallback/score.py \
  --cohort /var/tmp/psd-sqrt5-new \
  --baseline reports/2026_09_28_ds7_large_arm/baseline-01/rows.jsonl \
  --output /var/tmp/psd-sqrt5-new/hit-audit.json
```

`--dataset DS8` and `--dataset DS9` use the existing frozen DS8/DS9 extracts.
Their original baseline is
`reports/2026_09_28_arm_ds89_validation/baseline-v1/rows.jsonl`.
Supported methods are `full`, `sqrt3`, `sqrt5`, `log9`, and `guard5`. The latter
uses the fixed DS7-only threshold in `method-selection.json`. `coverage.py`
is a preliminary diagnostic; only complete `run_native.py` outputs establish
actual GLRT recovery. `summarize.py` assembles the recorded fixed experiment
folders and verifies full-control candidate equality against sealed results.

Requirements: the hash-bound saved-IQ extracts under `/var/tmp`, the original
four-rate exact/control template bank under
`/var/tmp/leo-arm-full-search-oracle-allrates`, NumPy, host GCC and FFTW.
`build.py --arm` additionally uses the recorded ARM cross-toolchain and float
FFTW archive; `--sanitize` produces host ASAN/UBSAN qualification builds.
`psd_probe.c` builds with FFTW double precision; exact host/cross compiler
commands are retained in `psd-builds.json`.

ARM inputs and selection are bound by `arm-inputs.json`; `arm-original.jsonl`
contains just their four already-computed original results. `run_arm.py`
reuses the frozen read-only saved-IQ transport, adds per-window masks from the
native PSD probe, and checks them against Python before running GLRT. It
requires the staged input symlinks and exported lower/upper banks in
`/var/tmp/leo-psd-arm-inputs-v1`; `export_psd_bank.py` records the bank format.
Hardware execution requires PLUTO+ 192.168.1.15 and the existing development
SSH credential. It is serial, uses CPU0 and performs no radio commands.

Validation:

```sh
.venv/bin/python -m pytest -q reports/2026_09_29_arm_psd_proposal
```

The C mask unit is run during host builds. On ARM, `test_mask --smoke2p5`
exercises a bounded subset; complete four-rate host and sanitizer tests remain
in the build receipts. Raw timing, native candidates, PSD outputs, masks and
hit audits are retained in the individual `host-*` and `arm-*` folders.
