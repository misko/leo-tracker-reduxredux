# Frozen-16 timing and robust-loss ablation

This is a fixed-finalist, candidate-pool-conditional comparison on the exact 553 tracks and 14,043 observations. It is not a full-catalogue global search. The 1, 0.5 and 0.25 second timing grids all remain within ±5 seconds. Tau and frequency offset are fitted using the saved randomized training mask. The legacy rows retain evaluation-selected identity for production parity; separate train-only rows expose that selection dependence.

The robust sensitivity uses training-only per-track frequency roughness plus a predeclared 250 Hz floor and pseudo-Huber loss (delta 1.5). It is not a calibrated measurement uncertainty model. Reused evaluation rows are conditional diagnostics, not untouched validation. See `results.json`, `track_diagnostics.json.gz`, and `timing_robust.png`.
