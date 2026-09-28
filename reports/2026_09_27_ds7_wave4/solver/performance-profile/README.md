# DS7 exact-baseline objective performance profile

This bounded, reference-free experiment profiles one frozen first-eight
objective/gradient call at the donor start and one at the sealed fitted theta.
It does not invoke the optimizer, read scores/pose/reference, or modify model
source. CPU and BLAS threads were fixed at one and the process ran at nice 19.

## Measurements

| Point | Profiled objective seconds | Offset profiler cumulative | Prediction cumulative |
|---|---:|---:|---:|
| donor | 2.972 | 2.682 | 0.189 |
| sealed fitted theta | 3.029 | 2.733 | 0.190 |

Peak RSS for loading the eight frozen documents and profiling both calls was
629,876 KiB. The two points are consistent: stationary-offset profiling consumes
about 90% of cumulative objective time, while geometry prediction consumes
about 6%. The fitted point is therefore not revealing a different late-solver
bottleneck.

Within the fitted-point offset profiler, the largest reported cumulative costs
were:

- `fit_stationary_offsets`: 2.716 seconds across 486 track calls;
- 19,097 scalar Brent root solves and wrappers: 0.391 seconds;
- 6,409 row quantiles and wrappers: 0.273 seconds;
- NumPy reductions: 0.467 seconds;
- root derivative evaluation: 0.315 seconds.

The `.prof` files in this directory retain the complete call statistics.
cProfile adds instrumentation overhead, so these seconds should locate costs,
not replace sealed end-to-end runtime measurements.

## Measured exact optimization candidate

The current implementation batches fixed-point iterations across candidates
within each track, but calls that kernel separately for all 486 tracks. A
read-only prototype grouped candidate rows across tracks with the same number of
training observations, invoked the unchanged offset kernel once per width, and
split results back to their tracks.

The first-eight input contains 6,409 candidate rows across 63 distinct training
widths. Across three alternating trials:

- current per-track offset stage: 2.017, 2.053, and 2.056 seconds;
- grouped-by-width stage: 1.592, 1.572, and 1.539 seconds;
- median stage speedup: **1.306x**;
- every returned offset matched exactly (`array_equal`);
- every convergence, gradient, and root-count audit dictionary matched exactly.

Because the stage is about 90% of profiled objective time, the measured stage
gain implies roughly a 1.27x objective-call improvement by Amdahl's law if the
integration overhead remains small. That is large enough to investigate and is
more consequential than optimizing geometry or log-sum-exp first.

## Cost and required gate

This candidate is not ready to install. The model currently profiles and scores
one track together. Cross-track batching requires separating residual
construction, offset fitting, and per-track density/gradient reconstruction.
It also creates larger temporary fixed-point tensors; grouping by training width
bounds them, but peak memory must be measured because full-88 is already memory
limited.

Before adoption it requires:

1. component tests covering repeated widths, duplicate quantiles, multimodal
   roots, and split/reassembly order;
2. objective, gradient, offset, audit, and response equivalence on frozen
   1/2/4/8 inputs at donor, interior, fitted, and near-boundary points;
3. peak-RSS measurement proving the larger temporary groups do not worsen the
   full-88 memory gate; and
4. sealed end-to-end timing, since cProfile and the isolated stage do not prove
   optimizer-level speedup.

No implementation change is made by this report. Even if the projected runtime
gain is realized, the separately measured full-88 retained-array estimate still
exceeds the 4 GiB envelope; cross-track batching addresses CPU, not document
residency.

