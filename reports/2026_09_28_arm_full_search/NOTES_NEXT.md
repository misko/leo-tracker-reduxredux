# Next full-coverage ARM optimizations

The measured 5 MHz window cost, about 11.85 seconds, is dominated by the full
coarse grid and fine acquisition. GLRT is already small. The next work should
therefore preserve all 11 overlapping 20 ms probes, 16 frames, 12 anchor
symbols, 11 reported CFO rows, dense epochs, and eight candidates, while
changing how the same sums are evaluated.

## 1. Compute absolute coarse correlations once for the whole dwell

The FP64 coarse kernel nests symbol, frame, epoch, template tap, and 12 CFO
lanes. For every 20 ms probe it evaluates a short sliding matched filter at
each absolute sample position, then normalizes it with a prefix-energy range
and accumulates the magnitude into the probe-local epoch/CFO cell. Eleven
probes spaced by 10 ms repeat the matched-filter work on their shared 10 ms.

Add a dwell-private coarse workspace indexed by absolute sample position.
For each of the 12 anchor symbols and each CFO, compute the complete sliding
correlation over the 120 ms receiver dwell once, preferably with bounded
overlap-save FP64 convolution. Compute the absolute received-energy prefix
once as well. Each probe then gathers the same 16 frame positions, applies the
same per-anchor normalization and magnitude, and accumulates into its full
11-by-epoch grid. This removes duplicated tap-level complex products across
overlaps and replaces the current per-window short-convolution loop; it does
not reuse or suppress candidate decisions.

Risk: FFT convolution changes floating-point association, and overlap-save
boundaries can shift or duplicate a sample. Qualify the absolute correlation
field against the direct kernel before grid comparison, including the first
and last valid positions. Candidate inventory/order is the scientific gate;
the existing FP64 grid tolerance remains a diagnostic. A direct whole-dwell
implementation should be retained as the oracle path.

## 2. Make `leo_fft_forward_range` a genuinely pruned FP64 transform

Fine acquisition currently builds one sparse template-weighted frame and calls
`leo_fft_forward_range` for every supporting frame of every retained candidate.
The private FP64 adapter ignores `first` and `count` and executes the entire
rate/500 transform: 5,000 bins at 2.5 MHz, 10,000 at 5 MHz, and 15,000 at
7.5 MHz. A candidate normally requests only the clipped 160 kHz interval at
500 Hz spacing, at most 321 consecutive circular bins. With eight candidates
and up to 16 frames, this is as many as 128 full transforms per window although
over 93 percent of each output is unread.

Implement a mixed-radix pruned-output transform for the existing radix-2/3/5
geometry. Propagate the requested circular bin set down the factorization and
evaluate only butterflies that contribute to those bins; retain the same
sparse input, FP64 roots, normalization, bin order, and 500 Hz grid. This
directly removes unused output work without narrowing frequency coverage or
frame support.

Risk: pruning changes butterfly order and therefore last-bit scores, especially
at radix-3 sizes. Differential tests must cover wrapped bin intervals, all four
rates, impulses, tones, and random sparse pilot inputs, followed by candidate
inventory/CFO/GLRT comparison. Avoid caching fine spectra across probes until
measurements show repeated absolute epoch hypotheses; that reuse is data
dependent and is not yet justified.
