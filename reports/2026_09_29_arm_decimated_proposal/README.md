# Reduced-resolution proposal correlation

Lag-1/3/5 complex products and power are constructed and frame-averaged on the
original template/sample grid. Only those completed feature arrays are averaged
in adjacent blocks of 1, 2, or 4 cells before centering, normalization, FFT
correlation, and ranking. Thus no IQ is decimated before lag construction.

Reduced length is `ceil(original_n/factor)`. A final partial block is divided by
its actual cell count. Template lag wrapping also occurs on the original grid.
Selected reduced bins map back to original epochs as `factor * bin`; the
existing downstream ±4 timing neighborhoods therefore remain unchanged.

Host builds retain the scalar fold and execute fold and decimation component
tests. ARM builds retain the qualified exact-order NEON fold; their parity and
factor-specific tests are cross-built only. Hardware runs and GLRT recovery
audits belong to the serial experiment owner.

The optional `factor4-reciprocal` build caches FP32 `1/support` for counts 1–16
and zero for unsupported cells. It replaces per-cell division with reciprocal
multiplication after original-grid folding. ARM processes four interleaved
complex cells at a time and retains a scalar tail. This changes FP32 rounding;
tests bound it against explicit division for every support count, extreme fold
values, partial blocks, reduced correlation scores, and all sample rates. It
does not enable global fast-math.
