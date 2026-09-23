# Second TRAIN full-group joint reassignment replication

Before fitting, retain all six 79-scan per-scan timing-model arms (two priors,
scales 0.2/1/5 s). Reuse the first group's catalogue scorer, 10-cycle ceiling,
stable-identities plus <0.001 Hz gain stopping rule, and monotonicity tolerances
1e-7 Hz for reassignment and 1e-9 Hz for polish. Preserve all track support.
Use the sealed conditional inference, unchanged helper code and verified cache
bindings. No true position, validation/test evidence or complementary frequency
rows enter inference. Seal every arm before held/reference evaluation. Retain
all settings, failures and cycle-limit outcomes. This is local alternating
inference conditional on the blind basin, not certified global optimization.
Four workers execute the six independent arms. Existing conditional TRAIN errors
are known; the choices here replicate the first group's settings without tuning.
