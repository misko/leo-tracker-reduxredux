# Continuous regularized timing search

This is a bounded continuous-position diagnostic using the frozen λ=1,000
Hz²/s² regularized timing profile.  Each track profiles its candidate identity
and constant CFO from randomized training rows, then its integer timing offset
is shrunk toward a per-scan latent shared center.  The center may absorb orbit
or propagation error and is not a physical receiver-clock estimate.

The objective is the existing duration-weighted, 800-Hz-capped training RMS
after that profile.  It is a heuristic regularized profile, not a joint MAP or
global likelihood.  Every fit starts from the same frozen in-window Sacramento
and Reno published-coordinate means plus their midpoint as the baseline and
robust searches.  At most 150 evaluations are allowed per seed.

`inference.json` sealed the selected coordinates before reserved rows and the
locked reference coordinate were evaluated.  The 48-scan window reached a
166.94 Hz capped reserved RMS, but its selected coordinate was 13.384 km from
the reference.  The 18-, 6-, and 1-scan selected errors were 8.194, 8.839, and
10.097 km.  The fixed-point timing improvement therefore did not translate to
continuous location recovery.

The sealed inference was produced before the later input-preflight/source-hash
hardening in this worker.  Its actual cache evidence and NPZ state inputs were
independently bound by [input_audit.json](../2026_09_23_position_model_generalization/input_audit.json).
That audit compares all day track/mask evidence to the frozen inventory and
hashes the numerical state files.  Do not interpret the current worker source
hash as having executed the sealed optimization.

For future runs, the worker validates the hash-bound dataset partition through
`load_partition`, verifies each active cache track digest against the frozen
inventory, verifies window authority, and records source hashes.  Reproduce a
new run only in a fresh output directory:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 .venv/bin/python \
  tools/research/position_regularized_search.py \
  --dataset reports/2026_09_23_position_train_val_test/dataset/manifest.json \
  --day-inventory reports/2026_09_23_day_position_validation/inventory.json \
  --replication-root reports/2026_09_23_day_position_validation/replication \
  --output /tmp/regularized-position-search --max-evaluations 150
```

The identity pool remains the conditional production-selected per-scan union;
this is not full-catalogue, independent, or prospective validation.
