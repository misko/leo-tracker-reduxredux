# Lower-edge residual: constellation and second-visit check

The strong shared residual in DS9-middle is not reproduced at comparable
strength in DS9-last. Both visits' pooled residual constellations appear as
broad central clouds without clearly separated levels. These observations do
not support assigning an additional bit alphabet to the residual. They also
do not prove that it is purely noise or that modulation is absent.

## Comparable inputs and method

Use the original paired soft caches for both visits, retaining the same 24
common nonpilot carriers and 45 eligible frames each. This avoids mixing the
expanded 28-carrier calibration of DS9-middle with the original calibration
of DS9-last. Verify each cache's inventory hash binding and record the cache
SHA256. Both receivers must pass held-pilot coherence >0.5 on each evaluation
frame. Known-state classification uses the existing receiver-checked assay at
symbols 194–225; every eligible frame passes that assay in this comparison.

Fit one complex gain per receiver/frame on symbols 226–257, then subtract the
state prediction on held symbols 258–289. Each receiver contributes 34,560
held complex observations per visit (45 × 32 × 24). These are not independent
bits, and shared residual correlation is not transmitter bit accuracy.

The mismatch controls repeat the shared-subtraction safeguard described in
[STATE_RESIDUALS.md](STATE_RESIDUALS.md). For separate real/imaginary statistics,
center each coordinate over frames, compare the paired signs, and compare
against every nonzero cyclic RX1 frame shift. This sign threshold uses the
whole selected frame set's coordinate means; it is an exploratory statistic,
not an independently trained decoder or a byte mapping.

## Results

| Measurement | DS9-middle | DS9-last |
|---|---:|---:|
| Raw complex shared correlation | 0.491 | 0.291 |
| Residual shared correlation | 0.246 | 0.018 |
| Maximum shared-subtraction mismatch control | 0.0066 | 0.0085 |
| Residual real-plane correlation | 0.250 | 0.016 |
| Residual imaginary-plane correlation | 0.242 | 0.021 |
| Centered real-sign agreement | 57.53% | 50.71% |
| Mean mismatched real-sign agreement | 49.82% | 49.99% |
| Centered imaginary-sign agreement | 57.51% | 50.47% |
| Mean mismatched imaginary-sign agreement | 49.81% | 49.99% |

The original 24-carrier middle cache reproduces the earlier expanded-cache
residual, so expanding carrier coverage did not create that finding. However,
the effect is much smaller in the second visit. Both real and imaginary planes
contribute comparably in DS9-middle; there is no evidence here that the residual
is exclusively a new imaginary-axis bit stream. The last visit's weak positive
correlation is not zero, but it does not reproduce the middle visit's magnitude.
Differences in signal quality and calibration remain possible explanations.

![Residual constellations](local/residual-constellation/constellations.png)

Each panel divides observations by its own residual RMS and clips the outer
1% by maximum absolute coordinate for display. No samples are clipped in the
numerical metrics. Density colors are local to each panel, and normalization
means their absolute noise powers cannot be compared from the figure. Pooling
over carriers and frames can hide a weak or varying constellation; the visual
absence of separated levels is not a modulation exclusion test.

## Consequence for the decoding effort

The late residual is currently a visit-dependent shared component with no
validated symbol alphabet. An unconstrained QAM clustering would turn a cloud
into arbitrary labels. The early header's independently corroborated changing
signs remain a stronger decoding target. Any further residual work should first
explain its dependence on visit, carrier, and calibration, and validate on
separate data before claiming information bits.

No satellite identity, orbit, position, timing field, or additional plaintext
was decoded. Both caches are previously studied data, not pristine holdouts.

## Reproduction

Run `residual_constellation.py` with NumPy, SciPy, and Matplotlib. Inputs are
read in place; source/method hashes, state labels, gains, residual arrays,
metrics, and the figure are under ignored `local/residual-constellation/`.
Synthetic tests verify plane-wise shared-signal versus mismatched-frame behavior
and removal of static coordinate bias. All 27 research tests and Ruff checks
pass. No raw recordings were modified, collected, downloaded, or committed.
