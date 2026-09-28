# Independent review: causal frequency reference with frozen geometry

## Statistical contract

The causal frequency density is a proper conditional mark density when evaluated with respect to
unit phase on the saved alias circle. The empirical joint count model and factorial set-density
terms remain unchanged. If `f_phase` integrates to one over unit phase, replacing the uniform mark
density adds `sum(log(f_phase))` to the old reference. The corresponding signal assignment ratio
must be `g_phase/f_phase = period_hz * g_hz/f_phase`; omitting the period would mix units and fail
uniform replay.

Each receiver needs a separate state. At a window timestamp, the implementation must construct and
score the density from strictly earlier nonempty candidate sets, then update. Empty windows advance
the clock but do not overwrite the last two nonempty sets. Reception and held-frequency roles share
one history with no reset. Exact duplicate phases may collapse in history because they define the
same mixture component, while every saved duplicate remains in the current set score and count.

The uniform birth component guarantees support across the circle. With no recent history, the
whole density is uniform. One-history mixtures and all two-history candidate-pair mixtures must
have normalized component weights; wrapped Gaussian components must be nonnegative and integrate
to one. Minimal circular velocity is a fixed modeling convention and does not infer a physical
alias branch or candidate identity.

## Comparison limits

The leave-one-record D/S/T coefficients, scaler, within centering, count reference, occupancy and
persistence were fitted under the earlier uniform-frequency reference. Replacing that reference
changes both the background density and signal/background ratio. Applying the old parameters is a
frozen transfer stress test, not an equal-opportunity refit or definitive model ranking. A loss can
show incompatibility of this frozen fit with the stronger reference; it cannot show that geometry
would fail after a causally valid training-only refit.

Uniform mode must reproduce every preceding temporal-transfer per-window reference, relative and
full score before causal results are interpreted. D/S/T and controls must share the same causal
frequency receipts, independent of satellite forecasts. Each control retains its own presence
filter history, while the observational frequency reference remains identical across arms.

Required executable checks include wrapped-density normalization and positivity, constant-velocity
prediction, duplicate-history invariance, empty/stale behavior, score-before-update, prefix/future
invariance, reference and ratio units, uniform replay, exact six-record/twelve-lane membership, and
source/input hashes. In particular, test a stale two-window history followed by a new nonempty
window and verify the next prediction uses only the new recent history.

No result was available for this pre-run review. The causal reference is an observational
candidate-frequency predictor rather than verified clutter. Neither improved full density nor
latent presence proves satellite identity, direction, or location accuracy.

## Outcome audit

The bounded run completed with exit code 0 in 28.48 seconds. The independent audit reconstructs
the causal history and phase density without importing the predictor for all 12 lanes and six
folds. It verifies 8,235 candidate-density values, including 981 uniform, 357 one-history and
4,100 two-history receiver/window predictions. It also verifies exact uniform replay against the
completed temporal-transfer artifact, causal-reference gains from per-candidate log densities,
and every exported equal-record mean and sign count. The audit passes and binds results digest
`2055db539d598e4633c97bf1ef5345d4e4bbada08292cb018793f95bfe43b587`.

On held-frequency windows, the causal observational reference improves over the uniform reference
by `+6.109846` nats/window, positive in all six records. This is the dominant result: recent raw
candidate frequencies predict later candidate frequencies far better than a uniform phase model.
It validates this fixed continuity reference as a stronger comparator, not as verified clutter or
a physical track.

Against that causal reference, frozen T contributes only `+0.012083` nats/window and is positive
in two of six records. T-minus-D is `+0.026572` and positive in all six; T-minus-S is `+0.019066`
and positive in five. T also exceeds swap by `+0.027525` and reverse by `+0.010142`, each positive
in all six, while T-minus-quarter-period-shift is `+0.020272` with four positive. These small
contrasts show that the frozen T emission is not wholly interchangeable with its controls under
this reference. They do not establish correct association or receiver direction, especially
because the coefficients and state parameters were fitted under the weaker uniform reference and
these reused records informed the diagnostic sequence.

The appropriate next decision is whether to specify a fully causal training-only refit against the
same continuity reference, followed by new-record confirmation. The present transfer result should
not be promoted as a fitted-model ranking or satellite-identity result.
