# Executable preparation and bounded launch

The frozen PREPARATION.md describes the earlier proposal state; its statement that the driver was not built is historical. The sealed `run.py` and `freeze.py` now implement that policy. Protocol SHA256 is0968450b726249af9b01101e0c8ee0c9b67c6bf6ec19374898ededcbfec18e9b, with2369 verified source hashes. Supplemental controller-flow tests live outside the immutable numerical closure and add no numerical behavior.

Four mathematical/layout/claim tests and four supplemental controller tests pass. Tests cover production106 fitter interface, copied starts for all four calls, c-arm isolation, qualification/fallback separation, retained failures, score admission and cached resume. Parity is checked before each arm's fits; an unexpected later-arm failure preserves earlier attempted results. Exclusive claims prevent automatic crash retries.

Parent authorized publication before execution, one worker at a time, shard0 then shard1. Each member reconstructs once and fits ordinary ECEF control and phase sensitivity from the same archived B7 seed per c arm. Each fit uses90 second soft budget and600 iterations; there is no hard interruption guarantee. The48 maximum fits preserve raw qualification and original archive fallback separately. Reference accuracy evaluation remains withheld until corresponding matched fits are terminal. This is a physical-model sensitivity, not a proven bug fix or production change.

Command, from repository root, changing the shard argument only after the preceding worker exits:

```bash
sudo -n env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 /opt/leo-tracker/releases/47e2705e437722daa5e6d6bb1c252d54b7a21dbc/.venv/bin/python reports/2026_10_10_position_error_iter130/run.py --shard 0
```
