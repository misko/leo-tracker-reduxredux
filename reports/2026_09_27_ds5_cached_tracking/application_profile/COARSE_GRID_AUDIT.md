# Exact coarse-grid work audit and next experiment

The measured coarse folded-anchor grid is the largest full-response cost: 682.6
ms of the 1,535.7 ms diagnostic call at 2.5 Msps and 3,065.5 ms of 4,476.2 ms at
5 Msps. The active backend is already AVX2/FMA, so another inner-loop SIMD variant
is not the next useful experiment.

The native kernel in `src/leo/analysis/starlink/_native_acquisition_grid.inc`
loops over anchor symbol, frame, local epoch, reference sample, then CFO. The
scientific grid has 11 CFO rows; execution pads it to 12 rows for vector shape.
For one 20 ms receiver probe, the exact loop inventory is:

| Rate | Epochs | Reference samples/symbol | Anchor symbols | Epoch positions across symbols/frames | Complex sample/reference/CFO accumulations |
|---|---:|---:|---:|---:|---:|
| 2.5 Msps | 3,333 | 11 | 12 | 580,680 | 76,649,760 |
| 5 Msps | 6,667 | 22 | 12 | 1,161,528 | 306,643,392 |

The full scanner makes 22 acquisition calls, so the selected dwells execute about
1.686 billion and 6.746 billion such accumulations respectively. Doubling sample
rate produces almost exactly 4x arithmetic because both epoch count and reference
width double. The observed coarse CPU ratio is 4.49x, consistent with this
quadratic work plus larger working sets.

An FFT matched filter is not an obvious win for these short kernels. A direct
batched implementation performs about 76.6 million complex accumulations per
2.5 Msps probe and 306.6 million at 5 Msps. A straightforward cached-kernel FFT
scheme still needs roughly 144 inverse transforms: 12 symbols by 12 execution CFO
rows. At transform sizes 65,536 and 131,072, that is approximately 151 million and
321 million radix-2 butterfly slots before pointwise products, normalization, and
packing. It also changes floating-point reduction order. This is not a credible
exact, large reduction at 2.5 Msps and is marginal on arithmetic count at 5 Msps.

The next bounded prototype should reuse direct correlations across the scanner's
overlapping probes. Eleven 20 ms probes cover one 120 ms dwell at 10 ms strides,
so acquisition currently submits 220 ms of receiver input. A full-dwell scheduler
can compute each symbol/CFO correlation at each absolute sample position once,
then assemble the 11 existing per-probe folded grids from those cached terms.

The prototype can preserve arithmetic exactly:

- Keep the existing short direct correlation kernel and its index/CFO accumulation
  order. Only memoize its complex result by receiver, anchor symbol, CFO, and
  absolute sample position.
- Retain each probe's current local power prefix. A global prefix would change
  floating-point subtraction operands and is therefore unsuitable for an exact
  candidate.
- Apply magnitude and the probe-local denominator exactly where the current
  kernel does, then add terms in the same symbol/frame/epoch order.
- Stream one anchor symbol at a time. At 5 Msps, one 600,000-position by 12-CFO
  double buffer is 57.6 MB; sequential receiver processing can keep total scratch
  below 96 MiB.
- Preserve all 11 scientific CFO rows, the discarded twelfth execution lane,
  support counts, output layout, peak ties, candidate order, and every full
  `DwellGlrt64Analysis` probe response.

The absolute ceiling from overlap alone is 220/120, or 1.833x for the correlation
portion. Removing 45.5% of the measured coarse stage would imply approximate
whole-call ceilings of 1.25x at 2.5 Msps and 1.45x at 5 Msps. Edge geometry and
cache assembly will reduce those gains. This cannot produce 10x by itself.

The experiment should freeze these rejection gates before outcomes:

1. `np.array_equal` for all 22 coarse score grids on both frozen profile cases,
   plus deterministic zero, CI16-extrema-derived complex samples, and a synthetic
   Qin pilot.
2. Exact serialized `DwellGlrt64Analysis`, including every probe/candidate, and
   exact `DwellDetection` on both real cases. Decision-only early exit is outside
   this full-response prototype.
3. At most 96 MiB candidate scratch per sequential receiver at 5 Msps.
4. With one warmup and three paired repetitions on P-core 0, at least 1.35x coarse
   stage CPU improvement at both rates and at least 1.20x complete-call CPU at
   5 Msps. Stop if either scientific or cost gate fails.
5. A 120 second total run bound, development cases only, with no holdout, RF, or
   production change.

An eight-tone sliding-sum formulation may reduce arithmetic further, particularly
at 5 Msps, but the stored complex128 Qin template contains rounded samples. Tone
decomposition changes the reduction and reconstruction path, so it is a separate
numerical detector variant requiring error and decision gates. It is not an exact
optimization proposal.
