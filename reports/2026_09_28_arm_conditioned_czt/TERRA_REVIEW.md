# Terra review: conditioned CZT screen

## Algebra and indexing

The proposed construction has the right Fourier-sign convention for the
existing regular grid.  With \(x_k=\texttt{weighted[k]}\),
\(\theta=2\pi(100)/\texttt{rate}\),

\[
a_k=x_k e^{-i\theta k^2/2},\qquad b_d=e^{+i\theta d^2/2}
\]

gives, at convolution index \(j\),

\[
(a*b)_j=e^{+i\theta j^2/2}\sum_{k=0}^{n-1}x_k e^{-i\theta jk}.
\]

The prefactor has unit magnitude, so `abs(c[j])` is the required magnitude.
There are two equivalent, but distinct, storage conventions.  With a shifted
linear array, store `b[d]` at `d + (n - 1)` and read the output at
`j + (n - 1)`.  With the proposed circular embedding, store `b[d]` at
`d mod L`; then the output is read directly at `j`.  Do not combine the
wrapped placement with the shifted output index.  The specified
`d=-(n-1)..Kmax-1` and `L >= n + Kmax - 1` prevent circular aliasing for every
requested `j` in `0..Kmax-1`.  FFTW's backward transform is unnormalised, so
divide its output by `L` before forming the score.

For the supported rates, `n=3333,6667,10000,13333` and `Kmax <= 41` imply
minimum powers of two `L=4096,8192,16384,16384`, respectively.  These are
adequate with either internally consistent embedding convention above.

## Contract and numerical review

`full_conditioned_scores` forms the baseline with
`rotate(-TAU*frequencies[0]*k/rate)` and then needs exactly the relative
regular-grid factors `exp(-i theta*j*k)`.  The CZT must be used only where the
current `regular` predicate is true.  A clipped endpoint still follows the
CZT path when it remains exactly `f0 + j*100`; only an actually irregular
index needs the existing direct FP64 path.  `f0` itself can be arbitrary: it
belongs in `weighted`, not in either CZT chirp.

The existing `128*FLT_EPSILON` guard was qualified for the short-lane blocked
dot screen.  It is not a demonstrated error bound for a float FFT/CZT: its
error also includes two transforms, pointwise product, inverse scaling, and
chirp generation.  Keep the FP64 recheck policy, but treat the guard as an
empirical qualification parameter and validate it for each supported length
and FFTW configuration; this review makes no formal guard proof.  Generate
chirp phases in FP64 before conversion to float if float FFTW is retained,
especially at `n=13333`, where the quadratic phase is large enough that
float-angle construction can add avoidable reduction error.

## Review of the current implementation

`conditioned_czt.c` selected the shifted-linear convention: it stores the
kernel at `d+n-1` and reads `n-1+j`.  That is consistent with its FP64 phase
construction, `L` scaling, and the direct-dot sign.  Its `n+64-1` allocation
bound is sufficient for the requested output segment even though the complete
linear convolution is longer than `L`; no wrapped term can reach the read
indices `n-1..n-1+nf-1`.  The full-search caller correctly bypasses CZT when
the complete grid fails the existing `regular` predicate, and leaves a
zero-denominator frame with no score contribution.

The refreshed raw-CZT unit test now covers `n=3333,6667,10000,13333`, `nf=1`
and 41, arbitrary `f0`, zero input, a coherent exact-bin tone, and a synthetic
adjacent-bin near tie.  It still checks raw magnitudes using an L1 amplitude
scale, rather than the normalized-score error used by the selection guard.
It therefore cannot alone validate selection retention.  The separate
`independent_czt_check.json` provides material empirical evidence for that
question: a host FFTWf calculation over 32 candidate searches from 16 saved
fixtures at all four rates, up to 16 frames and 41 bins, reports maximum score
error `3.778905366402796e-08` and retained every all-FP64 winner.  This is a
host numerical qualification, not an ARM or universal error proof.  The added
`test_conditioned_integration.c` closes the previous integration gaps: it
executes `full_conditioned_scores` for zero data and zero template energy,
verifies the explicitly irregular-bin FP64 fallback, and applies the production
near-max recheck rule to a coherent near tie before comparing its final winner
with an all-FP64 score.  Host 704 then supplies end-to-end evidence: all
123,904 candidate objects exactly equal the scoped reference and all 19,581
positive hits are retained.

No separate synthetic non-finite FFT-output injection is present.  Production
code explicitly rechecks a non-finite screen value in FP64, and all observed
host and ARM test outputs were finite.  This is a remaining branch-coverage
limit, not a blocker on the reported empirical result or a basis for a formal
floating-point guard claim.
