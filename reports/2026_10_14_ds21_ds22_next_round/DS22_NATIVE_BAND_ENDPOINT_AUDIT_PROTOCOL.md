# DS22-131 rejected native-band endpoint: zero-fit numerical audit

The sealed band-specific pilot selects a0.609km state but excludes a feasible state with an objective4963.52units lower and KKT0.00747449. The excluded low-origin fit reports optimizer success after21.29seconds. Diagnose that numerical stopping before interpreting the selected position as a model gain.

Bind the original low-origin best-feasible state and both-case sealed experiment. Preserve exact raw physical and nuisance coordinates, original25km disk, global prior and candidate bank. Use the existing endpoint-only chart; record any constructor timing-margin proposal without applying it. Replay original objective, NLL and KKT. No fit, reference, held or locked observation access.

After the initial replay, freeze the strongest centrally feasible coordinate in each of six original-chart blocks: geography, receiver/RF calibration, absolute satellite timing, original group calibration, shared logits and band contrasts. Use central steps1e-5 and1e-6, with no clipping or projection. If a block has no centrally feasible coordinate, retain that fact explicitly. Persist each objective input/value/full gradient immediately. Record complete raw gradient/constraint/nuisance-margin ledgers and the chosen probe inventory before side evaluations.

At each evaluated state, independently inspect native visibility, interpolation cells and temporal support. Report objective finite differences, gradient-derived curvature and estimated one-coordinate improvement relative to objective floating-point spacing. These are local coordinate checks, not a full Hessian or positive-definiteness certificate.

Maximum25objective calls and25explicit native predictions, plus two internal native predictions per band objective. Total120seconds including preparation, externalTERM135/KILL140. Zero optimizers and no retry or threshold relaxation. Any subsequent numerical repair requires its own frozen algorithm and matched control.
