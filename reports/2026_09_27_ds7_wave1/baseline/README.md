# DS7 corrected stationary baseline — wave 1

This directory contains reference-free, unscored direction-A evidence. No raw IQ,
pose file, score output, production write, or QNAP write was used.

## Frozen model and inherited assumptions

The port reproduces the corrected DS6 stationary model from repository commit
`75b76f66974c78588c6599822e8007aaa767466b`: Student-t4 at 100 Hz, stationary
penalized per-track offsets, a shared horizontal position, independent recording
timing offsets, the fixed 11.2 GHz prediction convention, and the sparse envelope
gradient. The local prior is the exposed DS6 development donor center
`[37.85625, -122.484375]`, with ±12 km east/north bounds and ±5 seconds timing.
Prior exposure is unaudited.

Candidate selection uses the original DS6 five anchors and training-only top-eight
union across 41 quarter-second timing values. Element selection uses the newest
element epoch per object among the latest causal provider snapshots while preserving
the baseline catalogue row identities. The installed public numerical port is
`ScannerTrackingInputStore.load`; `tools/ds7_export_baseline.py` contains the full
reproducible observation, shortlist, and bank builder.

The DS7 port deliberately initializes every recording timing offset at the same one
of `0`, `-2`, or `+2` seconds for each joint start. The historical DS6 multi-recording
joint run instead initialized each recording from its independent fitted offset and
also tried a zero-position start. This is the declared initialization delta; the
objective, bounds, profiler, gradient, and candidate policy are matched.

## Numerical admission

`pinned-oracle-audit.json` compares the port against AST-extracted pinned
`run_full.Stationary` and the pinned standalone `fast_solver`: offset difference is
zero, objective difference is at most `1.35e-11`, and maximum gradient difference is
`5.18e-7`. `oracle_audit.py` reproduces that comparison. The exact-propagation audit
at the smoke winner reports a maximum interpolation error of `0.0072503 Hz`.

Five component tests pass, including offset multimodality, WGS84 geometry, envelope
gradient agreement, deterministic partitioning, and negative input binding. Ruff
passes for both tools and their tests.

## Sealed unscored runs

- `smoke-final-a-v1` and `smoke-final-b-v1`: identical responses from identical
  source bytes; converged and interior; 24.34 and 24.25 seconds.
- `prefix2-solver-v1`: converged and interior; 56.97 seconds, 115 tracks, 49 total
  objective/gradient evaluations.
- `smoke-admission-unavailable-v1`: the earlier explicit admission receipt before
  corrected candidate banks passed their gates.

These are predictions, not accuracy claims. Scores are intentionally absent here.

Prefix-4 and group-8 are held unattempted. Prefix-2 consumed 56.97 of the 60-second
unit budget, leaving no credible margin for larger joint fits under contention. This
is a resource gate, not a scientific failure or abstention for those unattempted
units.

The arm is returned to `planned`. The repaired runner rejects privilege-changing
adapter wrappers. A future run must start the runner under a UID able to execute
`/opt/leo-tracker/current-api/.venv/bin/python` and then use the direct arm command.

## Reproduction commands

Observation export, per session:

```sh
sudo -n nice -n 19 env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  /opt/leo-tracker/current-api/.venv/bin/python tools/ds7_export_baseline.py \
  --plan reports/2026_09_27_ds7_evaluation_setup/plans/budgets/plan.json \
  --session SESSION --output reports/2026_09_27_ds7_wave1/baseline/exports/SESSION-tracks.json
```

Corrected shortlist and bank export:

```sh
sudo -n nice -n 19 env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  /opt/leo-tracker/current-api/.venv/bin/python tools/ds7_export_baseline.py --banks \
  --plan reports/2026_09_27_ds7_evaluation_setup/plans/budgets/plan.json \
  --session SESSION --tracks reports/2026_09_27_ds7_wave1/baseline/exports/SESSION-tracks.json \
  --output .leo/ds7-wave1/baseline/SESSION
```

Runtime recorded by the final adapter was Python 3.14.4, NumPy 2.4.6, and SciPy
1.18.1. Source hashes at closeout are recorded in `provenance.json`.
