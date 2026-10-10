# Frequency-grid errors: existing protection and two bounded next tests

Source/report audit only. No recording prediction, fit, new IQ, reserve access,
parameter tuning or production change. This is an unfrozen proposal.

## What B7 already models

[The current likelihood](../../src/leo/analysis/hard60_score.py#L21) wraps the
measured-minus-predicted residual at
`P = 1/(4.4 microseconds) = 227272.727... Hz`, then combines a 125 Hz Gaussian
satellite density with uniform clutter `lambda/P`. Satellite responsibilities
and clutter membership are recomputed jointly; sufficiently distant residuals
already lose influence through the clutter branch. The full
[wrapped-Gaussian oracle](../../src/leo/analysis/regional_position_score.py#L141)
includes periodic images; the narrow implementation omits images that cannot
affect float64 at its supported widths. Neither implementation includes
special shoulders spaced by the native CFO grid increment.

The [native conditioned estimator](../../src/leo/analysis/native_presence/presence.c#L711)
returns `acquired_CFO + signed_bin * Delta`, where **Delta=P/512=443.892... Hz**.
These neighboring grid bins are not extra physical symbol-rate aliases at P.
A ±Delta component mixture would model estimator peak errors, not a newly
discovered physical ambiguity. Acquired CFO varies continuously, so published
tracking CFO alone is not a universal 443.892 Hz lattice observation. The
public [TrackingCandidate](../../src/leo/contracts/scanner_tracking.py#L72)
port exposes fractional tracking CFO but not the acquired CFO or native
residual-bin index. Some underlying published analysis candidates retain
acquired/residual CFO; provenance-specific public adapters would be needed to
recover them without changing immutable contracts.

At one-grid-bin residual the Gaussian factor relative to its peak is about
`exp(-.5*(443.892/125)^2)=.00183` before other satellite/clutter terms. Such a
measurement can consequently become clutter or attach to a competing satellite.
That is an existing robust behavior, not proof that the measurement was wasted.
An estimator-error shoulder would preserve some influence but could also make
incorrect satellite explanations easier to support and introduce more minima.

## Why iteration120 does not identify mixture weights

[The synthetic screen](SYNTHETIC_RESULTS.md) supplies the true acquired CFO and
places the signal exactly on residual bin zero. It establishes amplitude- and
support-dependent conditional errors, including one +3Delta case, but does
not sample unknown within-bin frequency phase, acquisition error, fractional
timing admission, candidate competition or operational signal/noise conditions.
Its 16 seeds per cell cannot supply a universal ±Delta mixture weight. A
three-component ±Delta model would also miss the observed +3Delta event.

Ordinary nearest-bin rounding with uniformly distributed within-bin phase has
standard deviation `Delta/sqrt(12)≈128.14 Hz`, close to B7's 125 Hz. This is an
arithmetic comparison, **not** evidence that B7's width was calibrated to that
mechanism. Adding independent quantization noise to the current width could
double-count an effect already represented approximately. A bin-integrated
Gaussian model would require conditioning on each acquired grid origin and a
separately justified pre-quantization error distribution; it does not follow
from the published scalar CFO alone.

Available margin, exact/control scores, sample rate and reconstructed support
are useful diagnostic strata. None is calibrated SNR, actual emitter-on
occupancy or CFO variance. See [111 input audit](../2026_10_09_position_error_iter111/MEASUREMENT_INPUT_AUDIT.md).
Support geometry describes what the estimator inspected, not what signal
contributed. Do not use the proposed receiver geometry's occupancy to choose
tail weights and then interpret the resulting fit as independent evidence.

## Two lean matched tests, in order

**1. Preferred next measurement test: off-grid conditional transfer.** Freeze
a small synthetic grid of injected residual phases within one Delta relative
to a fixed acquired CFO, independently specified signal amplitudes and the
same full/partial support cases. Generate the actual complex frequency ramp;
keep each noise realization and signal amplitude matched between complete and
partial support. Call the same native conditioned estimator, retain every
margin success/failure and report residual error in Hz and bin units. Keep
noise independent of the on/off mask. This separates ordinary rounding from
multi-bin peak errors and can falsify a symmetric, fixed-bin-error assumption.
Do not fit probabilities from the already inspected 120 cells or treat supplied
acquisition as blind operation. A later independent seed set would test a law
specified from this measurement experiment; no real-data position tuning is
needed. Precise call budget and constants require a separate predeclaration.

**2. Conditional positioning sensitivity only if the first test supports tails:**
use a two-scale wrapped Gaussian signal density,

`g_e(r)=(1-e) WN(r;0,125^2) + e WN(r;0,tau^2)`.

This is cheaper and less multimodal than adding many ±Delta shoulders. It
represents broad estimation error without asserting that every real residual
is an integer bin slip. `e=0` must reproduce B7 objective, responsibilities and
prediction gradients exactly. For positive e, normalize both components and
sum their derivative contributions before calculating satellite responsibilities;
keep the existing clutter and detection normalization unchanged. At most one
global `(e,tau)` pair should advance, fixed by an independently tested
measurement law before position outcomes are read. **No numerical pair is
justified by the present audit**, so no candidate fit is authorized or ready
to freeze. If a merely arbitrary sensitivity pair is used instead, label it
explicitly as a robustness stress test, not an estimator-derived model.

The positioning comparison must retain all DS16/17/18 members, observations,
satellite bank, physical/clock priors, same fitted-derived starts, 90 s/600
iteration budgets and the independent .001 qualification gate. Compare
e=0 and the single candidate under both c=0 and fitted-c, locking both static
and time-dependent RF terms in c=0. Retain archive and same-start controls,
all failed attempts, fallback counts and coverage. Frequency density/score,
responsibility changes and localization metrics are separate; neither lower
NLL nor extra satellite assignments demonstrate improved positioning. Use
randomized whole-recording/dependency groups for any calibration/validation,
keep both receivers together, and label all historical cohorts consumed.

## Prior work and identifiability limits

[106](../2026_10_09_position_error_iter106/RESULTS.md) already tested globally
narrowing 125 to 100 Hz across all 148 records: some central metrics improved,
but the complete comparison did not justify promotion. Repeating scalar width
tuning is not this proposal. [Earlier GLRT mark prototypes](../2026_10_07_glrt_mark_prototypes/README.md)
tested rank-based signal odds and precision without reliable improvement;
only 130/320 fits qualified, and archived upstream calibration had reference
dependence. They do not validate a margin-to-variance map for B7. A
[historical localization panel](../2026_10_01_localization_approaches/README.md)
already used Student-t4: a generic heavy-tail suggestion is not a novel physical
explanation, and that different pipeline is not a matched B7 comparison.

Frequency tails remain confounded with receiver clocks, satellite timing,
RF-dependent c, association mistakes and orbit/model errors. Broadening can
hide all of them and weaken geometry. The minimal justified action now is
the off-grid measurement test; a fixed estimator-derived alias mixture is
not yet supported, and no sub-kilometer improvement is predicted.
