# Frequency-estimator effective time: a bounded analytic hypothesis

Source/mathematical preparation only. No synthetic computation, recording access,
model fit, reference-position query or accuracy claim accompanies this note.
Iteration 151 currently occupies both numerical research slots. This is a
follow-up to the unresolved issue in [118](../2026_10_09_position_error_iter118/INTEGRATION_SUPPORT.md),
not a claim to have discovered or validated a new correction.

## The relevant estimator

[125's refinement](../2026_10_09_position_error_iter125/refine.py) reconstructs the
same sum of per-frame 64-symbol coherent powers used for CFO refinement. Frames
are combined in power, rather than coherently across their arbitrary phases.
The symbol step is 4.4 microseconds. Its constant-frequency synthetic studies
and the later sub-bin comparisons do not determine the response to a chirp.

For a deliberately restricted, noiseless, correctly matched single-signal model,
let symbol correlation m in frame j be

`z_jm = a_jm exp(i phi_j + i 2pi [f0 t_jm + kappa t_jm^2 / 2])`,

where `a_jm >= 0` includes any actual estimator normalization and support mask.
For this derivation it is fixed as frequency varies. The power objective is

`P(q) = sum_j |sum_m z_jm exp(-i 2pi q t_jm)|^2`.

A common positive normalization independent of q does not change its maximizer.
Using within-frame times for the trial rotation gives the same power: the
additional frame-wide phase cancels. This does not allow coherent frame summing.

## First-order chirp response

Write `Delta_mn = t_jm - t_jn` and `M_mn = (t_jm + t_jn)/2`. Expanding the power
into within-frame pairs gives cosine terms with phase

`2pi Delta_mn [(f0 - q) + kappa M_mn]`.

Near a uniquely identified coherent peak, when these residual phases are small,
the quadratic cosine approximation implies

`q_hat = f0 + kappa t_eff + higher-order terms`,

`t_eff = sum_(j,m,n) a_jm a_jn Delta_mn^2 M_mn
         / sum_(j,m,n) a_jm a_jn Delta_mn^2`.

Diagonal pairs contribute zero; ordered versus unordered pairs give the same
ratio. A zero denominator means this approximation identifies no CFO. It must
be reported as an admission/identifiability failure, not repaired by a ridge.

The important distinction is that effective time is weighted by within-frame
frequency curvature. It is generally not the arithmetic mean of symbol centres.
For an equal-amplitude symmetric frame it equals that frame's centre. Identical
complete frames also have equal curvature weights, recovering the ordinary
centre when their times are symmetric. This is an exact no-correction case for
the first-order expression.

For N equally weighted consecutive symbols of step d, the ordered-pair curvature
weight is `N^2 (N^2 - 1) d^2 / 6`. Thus partial-frame curvature does not scale
linearly with symbol count. This observation alone establishes neither the
real estimator's amplitudes nor a useful position correction.

Because the restricted weights are nonnegative, t_eff lies between the earliest
and latest contributing within-frame pair midpoints. A loose leading-order bound
relative to the stored support centre t0 is

`|q_hat - f(t0)| <= |kappa| max |M_mn - t0| + higher-order terms`.

This is a frequency-scale bound, not a position-error bound. Turning it into a
position claim would require the fitted model's actual identifiability and
nuisance coupling. No reference-location derivative or per-scan tuning is allowed.

## What remains unproven

Noise, interfering signals, symbol normalization and detection conditioning can
make correlation amplitudes/phases incompatible with this simple model. A coarse
frequency-grid winner and the bounded local refinements can also obscure the
continuous peak. The formula is therefore a falsifiable oracle for a restricted
synthetic experiment, not an operational timestamp replacement.

Before any recording replay, inspect the native correlation normalization and
verify that a synthetic oracle supplies the same symbol array and power as the
actual estimator. Then freeze tests covering zero chirp, symmetric support,
asymmetric support, reflected support, sign-reversed chirp, and shifted time
origin. Separate continuous-peak behavior from coarse-grid/sub-bin error. Retain
all missing or ambiguous peaks. Choose the chirp grid by dimensionless phase
excursion over the declared support, before results; do not choose it from
position errors or present stress values as measured satellite dynamics.

The first prospective stop condition is failure of the predicted sign, symmetry,
or first-order limit in this restricted model. If it passes, the next question is
whether existing public support metadata determine the necessary weights at all.
Without that link, a free per-window time offset is not justified. A negligible
frequency-scale effect should stop the proposal before expensive position fits.

Any eventual recording comparison must retain identical observations/admission,
candidate policy and budgets, matched final c=0/fitted-c arms, and separate
frequency-fit versus position metrics. No execution protocol is frozen here.

## Source inspection: normalization and support

Read-only inspection of `src/leo/analysis/native_presence/presence.c` lines
650–721 confirms that the estimator accumulates raw complex correlations for
64 symbols, sums each frame's FFT power, and divides the final maximum by
`sum_j (sum_m abs(z_jm))^2`. This denominator is common to all residual CFO
bins for a fixed correlation workspace, so it cannot change the bin winner.
There is no per-symbol amplitude normalization in this accumulation. Frame
phase cancels in each power as assumed above. This source agreement is not
synthetic or numerical parity evidence.

The native loop admits complete 64-symbol rows, falling back to the earlier
symbol range when needed and stopping at unsupported rows. Consequently the
partial-frame example above is a mathematical stress case, not evidence that
this native implementation emits partial frames. Unequal signal amplitudes
and differing admitted frame centres remain possible sources of weighting.
Raw sample interpolation and correlation across each symbol also mean that
the point-sample chirp model requires a separate sample-level validation.

The private native-GLRT copy has the same accumulation structure but an
experimental magnitude helper and optional precomputed rotations. An eventual
test must bind the actual backend used by the observations; inspection of one
copy does not establish deployment parity. No source was changed and no
numerical computation was run for this inspection.
