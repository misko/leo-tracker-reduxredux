# Differential drift correction: fixed-position comparison complete

Implemented a training-only correction layer for the three declared receiver
anchor assumptions. Six tests pass, and the exported-track census reproduces
the published alignment model's qualification and coefficients. No position
fit, new geographic error, or sub-km result has been produced in this report.

**Integration is now complete on all eighteen original panels.** Every unchanged
arm replays the published training score, gradient, per-track held score and
candidate weights. [Complete fixed-position results](FIXED-RESULTS.md) compare
the three allocation assumptions. Holding RX1 unchanged improves held scores
on 12/18 panels, the symmetric split on 10/18, and holding RX0 unchanged on
4/18. Each ties on one panel without corrections. This supports testing the
allocation sensitivity geographically, not promoting a hardware calibration.

| Dataset | Qualified pairs | Symmetric correction: tracks / exported tracks | Scans with corrections / sampled scans | Tracks corrected under either single-receiver anchor |
|---|---:|---:|---:|---:|
| DS7 | 68 | 136 / 1,437 | 10 / 24 | 68 |
| DS8 | 37 | 74 / 1,438 | 8 / 24 | 37 |
| DS9 | 50 | 100 / 1,460 | 8 / 24 | 50 |

The symmetric arm changes 310/4,335 exported tracks (7.15%) across 26/72 scans.
All other tracks remain present and unchanged. Each single-receiver anchor
changes half as many tracks. These are all exported tracks; the geographic
model's 4,328 bank-eligible tracks require a separate coverage check.

The 155 qualified pairs here exceed the earlier 145-target main comparison
because this correction does not require held coverage or qualification of the
unused timing-like arm. Every qualification decision uses training data only.
The census checks every drift fit against the published alignment artifact.

The relative difference cannot identify the receivers' common drift. The three
arms therefore fix different assumptions: equal split, RX0 unchanged, or RX1
unchanged. Synthetic tests demonstrate that all three can remove relative drift
while disagreeing about common Doppler. None is a measured hardware calibration.
Corrections remain pair-specific omitted-target estimates, not a single shared
hardware clock fit. Earlier pair selection used target training data, and does
not establish shared satellite identity.

Tests cover injected recovery, common-mode ambiguity, receiver swap symmetry,
held isolation, target-response exclusion, exact unchanged/zero correction,
missing-calibration fallback, track preservation and binding/donor gates.
[Test output](tests.log). The census completed with exit code zero under a
60-second timeout, BLAS1 and nice19. It verifies source hashes and preserves all
track IDs and observation counts. No candidate banks, propagation, new RF,
raw IQ, provider requests or production components are involved.

[Protocol](PROTOCOL.md), [correction implementation](correction.py),
[coverage and per-track receipts](coverage.json), [coverage seal](coverage-seal.json).

Bank-eligible coverage is now verified: the symmetric arm changes 310/4,328
tracks, still across 26/72 scans. Every uncorrected track's training and held
scores remain unchanged at the fixed positions.

Remaining work: freeze and run a bounded three-allocation geographic
comparison with all fallbacks and numerical failures retained. Geographic and
held-prediction outcomes must be reported separately. Do not select an anchor
using the exposed unsurveyed reference coordinate.
