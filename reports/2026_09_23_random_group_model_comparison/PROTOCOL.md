# Random-group model comparison: declared before new fits

Use the seed-20260923 manifest in `../2026_09_23_position_random_group_split/`.
Read only its 68 training and 22 validation recordings. Do not open the 23
retrospective-test recordings in this experiment. All partitions are historically
exposed; a newly enforced access boundary cannot erase prior exposure.

## Common validation windows

Evaluate each complete validation group and its first recording:

- `utc2h-20260922T1800Z`: ten recordings; first `scan-fw-f835999e917f8264`.
- `utc2h-20260923T0800Z`: twelve recordings; first `scan-fw-9f976649d8b948db`.

Record exact session lists, elapsed span and summed nominal capture time. The
single-scan cases are nested within the group cases, not independent replicates.
Do not stitch the two groups together and describe them as continuous capture.
Two groups are inadequate to establish a reliable tail-error distribution.

## Models and separation

SOL compares the ordinary duration-weighted capped 800 Hz objective, the existing
duration-weighted track-level pseudo-Huber objective at 150 Hz, and an equal-scan
outer-weighted version of that robust objective. Keep the within-scan duration
weights fixed. Equal scan weighting is a dependence-control heuristic, not a
fully specified correlated likelihood. Assess scan influence where affordable.

Terra compares hard identity selection with a normalized candidate mixture and
an explicit null/outlier component. Define candidate priors on the full cached
pool: changing visibility must not renormalize away missing signal support.
Freeze mixture scale and null settings before validation spatial inference;
record any training selection. Profiling nuisance parameters is not Bayesian
marginalization, and soft weights are not calibrated identity probabilities.

Use saved randomized frequency masks. Window-specific location, identity, timing
and CFO may be inferred from its training frequency rows. Reserved frequency
rows report prediction quality only; they must not select a seed, location or
nuisance solution. Hyperparameter fitting uses only the recording-level training
partition. Use the same own-window published Sacramento/Reno mean and midpoint
seeds, constrained to the Sacramento-250/Reno-500 km intersection.

Both seeds and candidate pools were historically response-conditioned. Therefore
these remain conditional refinement experiments, not independent full-catalogue
acquisition. Preserve all attempted methods and windows, including failures.

Save inference and hash receipt before scoring reference-coordinate error. Use
the same locked reference as earlier reports only for post-seal evaluation.
Report common reserved capped and uncapped RMS separately from native objectives,
runtime, convergence, all geographic errors, and limitations of uncertainty.
Do not tune against geographic validation error.

## Independent numerical audit

A separate SOL audit compares cached quarter-second state interpolation against
exact propagation on training-only examples, including timing-grid endpoints.
Report errors before and after removal of a constant frequency offset. The
purpose is to distinguish numerical approximation from physical/model error;
small interpolation errors would not validate the TLEs themselves.

No RF collection, production deployment or prospective-test access is authorized
by this comparison. Retain existing cache files and preserve concurrent changes.
