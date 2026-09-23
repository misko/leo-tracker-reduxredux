# Second TRAIN timing-model replication

Declared before these fits: replicate both global and per-scan epoch models on
all eight baseline arms (1/6/16/79 scans, Sacramento/Reno), at scales 0.2/1/5 s.
This is 48 fits, with unchanged helper implementations, baseline identities,
training masks, altitude zero, timing bounds, visibility rule and CFO profiling.
No parameter choice uses the second group's geographic errors. The baseline
errors have already been inspected; this is TRAIN development, not validation.

Verify the sealed baseline, its source and cache bindings, and exact membership
in the second frozen TRAIN group before fitting. Check zero-epoch objective
parity. Keep unsuccessful solver outcomes and exceptions. Seal all fits before
evaluating complementary rows or reference error. No VAL/TEST evidence is read.
Parallel workers execute independent prior/view/model tasks; each reuses its
prepared tracks across all three scales. Numerical source and protocol hashes
are bound into the inference. Fits are conditional on blind baseline identities;
these are empirical nuisance models, not physical timing measurements.

Compare every arm's error, held RMS, visibility/boundary failures and stopping
diagnostics. Starts and nested duration views are not independent replicates.
Replication is required before selecting a small model suite for validation;
neither lower frequency residual nor synthetic recovery proves field accuracy.

The first launch failed before any fit because sealed baseline inference stores
locations but not per-track assignments. The runner reconstructs assignments
at those locations using the original training-only scorer and checks objective
parity. It never reads the baseline post-seal result file.
