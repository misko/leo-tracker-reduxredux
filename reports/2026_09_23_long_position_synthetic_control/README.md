# Direct-SGP4 synthetic position control

This bounded control separates a numerical or optimizer failure from mismatch
between the position model and real radio data. It does **not** establish real
position accuracy and does not satisfy the requested sub-300 m long-duration
positioning goal.

The frozen protocol used the first six TRAIN scans, their 476 real track
supports, timestamps, and randomized masks, plus the sealed Sacramento
fixed-identity assignments. For each scan, the generator resolved the exact
recorded causal TLE snapshot and ran direct SGP4 at every exact rounded
observation epoch. The synthetic site was 38.0, -122.0 at ellipsoidal altitude
0 m. All 476 assigned satellites were above its geometric horizon for every
sample, so no track was excluded; the result remains conditional on this
fixed, visibility-qualified support. The run contains 8,285 observations.

The fitter knew the generating identities but not the generating coordinate.
It read the materialized state NPZ once, held epoch at zero, eliminated one CFO
per track from training rows, and solved location from both original prior
centres inside their original disks. Truth and held-row metrics were added only
after the six fit records were sealed.

| Synthetic case | Sacramento start error | Reno start error | Train RMS | Held RMS |
| --- | ---: | ---: | ---: | ---: |
| zero noise | 0.000 m | <0.001 m | <1e-7 Hz | <1e-7 Hz |
| independent 300 Hz noise | 369.913 m | 369.913 m | 285.326 Hz | 321.251 Hz |
| same noise + per-satellite epoch shift | 1,479.544 m | 1,479.544 m | 290.960 Hz | 326.426 Hz |

Both starts converged in all cases and agreed to numerical precision. The
frozen noiseless recovery check passed for both starts, with error below 0.3 km
and train/held residual RMS below 0.01 Hz. The held-frequency invariance check
also passed: adding deterministic held-only perturbations of at least 1 MHz
left all six fit and convergence records bit-identical.

The exact noiseless recovery establishes internal consistency between this
shared generator and fitter and rules out a local optimizer failure on this
support. It also shows that the two distant starting centres reach the same
solution. Because both sides use the same Doppler equation, frames, and SGP4
implementation, common-mode physical or implementation errors can cancel; this
control does not independently validate their correctness or the real-data
pipeline. The 300 Hz draw landed at 370 m, just outside 300 m, and the added
seeded 0.3 s per-satellite epoch-shift draw increased error to 1.48 km. That
shift is a sensitivity case, not a calibrated orbit-uncertainty distribution.
These outcomes are not substitutes for real measurements. They support
investigating real-data/model mismatch while showing that sub-300 m is not
robust to the tested noise realization.

`materialization.json` contains every inclusion decision, realized CFO, epoch
shift, snapshot digest, and input binding. `materialized.npz` is object-free
and contains the direct base and shifted states plus all three synthetic
frequency cases. `results/inference.json` is the pre-truth sealed fit record;
`results/results.json` adds the post-seal truth errors, held residuals, and
checks. `SOURCES.sha256` binds the protocol, executable sources, materialized
inputs, results, and plot.

The first fit publication attempt is retained under
`results_superseded_preseal_held_metrics/` with its exact executed fitter and
hash manifest. Its optimizer used training rows only, but its sealed inference
records mistakenly calculated and exposed held RMS values. The corrected
publication removes those fields before unsealing; `fit_parameter_parity.json`
records exact equality of fitted parameters, training objectives, and
convergence fields between the two attempts.

Reproduction requires read-only service access to the TLE archive for
materialization:

```bash
sudo -u leo env PYTHONPATH="$PWD/src" "$PWD/.venv/bin/python" \
  reports/2026_09_23_long_position_synthetic_control/materialize.py \
  --manifest reports/2026_09_23_long_inventory_complete/manifest.json \
  --baseline reports/2026_09_23_long_training_search_multi/results/results.json \
  --cache-root /tmp/leo-long-training-cache-first16 \
  --tle-root /var/lib/leo/tle \
  --output /tmp/long-position-synthetic-materialized.npz \
  --receipt /tmp/long-position-synthetic-materialization.json

uv run python reports/2026_09_23_long_position_synthetic_control/fit.py \
  --materialized reports/2026_09_23_long_position_synthetic_control/materialized.npz \
  --materialization-receipt reports/2026_09_23_long_position_synthetic_control/materialization.json \
  --output reports/2026_09_23_long_position_synthetic_control/results
```
