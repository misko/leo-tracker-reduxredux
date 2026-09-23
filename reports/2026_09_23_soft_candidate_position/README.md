# Normalized soft candidate refinement on random validation groups

This is a bounded conditional-refinement experiment, not independent acquisition
or a calibrated satellite-identity posterior. The seed-20260923 dataset supplies
two validation groups of ten and twelve scans. Each full group and its first scan
are evaluated; the 23 retrospective-test recordings are not opened.

The hard control minimizes equal-track mean training MSE after profiling one CFO
and selecting a candidate and integer timing offset per track. It differs from
the duration-weighted capped baseline in the grouped-robust experiment.

The soft arm averages per-track negative log mixture likelihood divided by its
training sample count. Signal components have a predeclared 250 Hz Gaussian
scale, a uniform prior over the complete candidate-by-timing support and total
prior mass 0.5. Invisible components retain their prior mass but have zero signal
likelihood. A constant-frequency null component has scale 30,000 Hz and prior
mass 0.5. Each component's CFO is fitted only on training frequency rows. These
settings are fixed before validation fitting; there is no geographic tuning.

Dense frequency rows are not independent, so this IID likelihood is a heuristic.
Timing and CFO are profiled, not marginalized; weights must not be interpreted as
calibrated identity confidence. Null probability and component entropy are
reported to expose degenerate solutions.

At each selected location, native reserved error is the posterior expectation of
squared residual using the **training-frozen** component weights and CFOs. It is
not the error of the posterior mean waveform. Common capped and uncapped RMS
instead use the same hard training-MAP candidate/timing/CFO scorer as the other
experiment, with one-second occupied-bin duration weights. Comparing these
different statistics as if they were identical would be misleading.

The three seeds are the own-window published Sacramento and Reno coordinate
means and their midpoint, constrained to the same prior intersection. Historical
candidate and seed discovery used response data, so this is conditional on that
support. The reference coordinate is introduced only after inference is saved
and hash-sealed. `results.json` includes all fits, coordinates, convergence,
common and native scores, input hashes, source hashes and runtime. Nothing is
deployed and no new RF is collected.

Reproduce in a fresh output directory:

```bash
PYTHONPATH=src .venv/bin/python tools/research/position_soft_candidate.py \
  --manifest reports/2026_09_23_position_random_group_split/manifest.json \
  --inventory reports/2026_09_23_day_position_validation/inventory.json \
  --replication-root reports/2026_09_23_day_position_validation/replication \
  --output /tmp/position-soft-reproduction
```

The [common report](../2026_09_23_random_group_model_comparison/README.md) compares
geographic errors across all methods without treating native scores as equivalent.
