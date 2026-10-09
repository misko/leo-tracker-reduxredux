# Independent interpretation review: receiver-pair contrasts

This review changes no frozen source, input, hyperparameter, operational selection
or production behavior. It does not access reserves or newer outcomes. No numerical
worker was launched. The review concerns what the paired diagnostic can establish
and one simple subsequent position experiment, not a measured accuracy improvement.

## Partial observation, not a cohort conclusion

At **2026-10-09T16:03:22Z**,12 readable member receipts were complete, with no failed
or mid-write receipts in that snapshot. Both arms had exactly3069 pairs. Summed
possible contrast dimensions were62; summed data rank was57 after linear/channel
projection and50 after existing smooth-clock projection. These are correlated
per-recording dimensions, not57 or50 independent physical mechanisms. They are
early acquisition-order coverage, not a randomized sample. Full148 results and all
failures must be reported before choosing an experiment from the observed patterns.
The workers254765/254766 were authoritatively running at16:02:31Z.

Rank equality between arms is expected: assignment membership, times, channels,
weights and smooth-clock design are shared. Rank depends on those designs rather
than the residual values. It is not evidence that c has no frequency effect.

## What the diagnostic establishes

The [exact pair join](paired_join.py) retains satellite/channel/rounded-ms identity
and duplicate provenance. Averaging the existing smooth-clock design identically
to the residuals makes the subsequent nuisance projection algebraically meaningful.
The [tested small solver](../2026_10_09_position_error_iter88/linear_contrast.py)
finds the stated weighted, zero-sum, ridge-regularized linear solution without a
pair-count-square projection matrix. Synthetic tests verify its augmented least
squares/KKT equivalence and confounding behavior.

Lost contrast rank establishes that some satellite-labeled residual directions
are indistinguishable from the supplied common time/channel/smooth-clock span on
these observations. Surviving numerical rank establishes only linear independence
under the numerical tolerance. Neither finding assigns a physical cause.

## Physical-identifiability pitfalls

1. **A common satellite frequency offset largely cancels in RX1 minus RX0.**
   Satellite-indexed pair residual structure can reflect different receiver clocks,
   RF/channel dependence, time coverage, association mistakes, or receiver-specific
   signal effects. It does not establish a satellite oscillator correction.
   Rounded-ms keys also retain actual receiver-time means; timestamps and Doppler
   slopes can produce a small difference that should remain visible in provenance.
2. **Smooth projection is unpenalized and unconstrained.** It asks whether an effect
   lies in the existing clock-function span. Actual B7 clock coefficients have
   regularization and bounds. Projection may absorb patterns requiring implausibly
   large/rough coefficients or overfit finite data. Rank loss does not prove the
   production clock model would or should absorb that pattern.
3. **Numerical rank is not reliable signal identification.** A barely nonzero
   singular mode can exceed the machine-tolerance cutoff while being too weak to
   estimate at the working noise level. Regularized rank describes prior-supported
   algebra, not information supplied by observations. Report singular values,
   data-null modes and shrinkage separately before claiming an identified effect.
4. **The pair precision is a working assumption.**1/31250Hz² assumes independent
   equal125Hz window residuals. Correlated adjacent windows, receivers and assignment
   conditioning violate that simplification. Duplicate averages receive no extra
   precision, intentionally. No uncertainty interval or physical noise calibration
   follows from the prior width or pair counts alone.
5. **Assignments are fitted-derived and selected by confidence.** Both arms share
   fitted-B7 assignments above0.5, so the comparison is conditional on that model.
   Misassociation can remain confident; unassigned and unsupported observations are
   explicit, but the paired subset need not represent the entire recording.
6. **Common effects and zero-sum shrinkage change the quantity being summarized.**
   Raw satellite means contain a common intercept; zero-sum shrinkage removes a
   common direction and shrinks weak groups. Lower mean absolute contrast versus
   raw values is therefore partly algebraic, not evidence of a discovered hardware
   error. Group-balanced and pair-balanced summaries describe different populations.
7. **In-sample residual reduction is expected when adding background columns.**
   [Report](report.py) reconstructs fitted background, remaining contrast/residual
   and final residual RMS on the same eligible pairs. Those numbers are descriptive
   and do not form a physical additive variance decomposition. Lower RMS cannot
   substitute for matched downstream position error and an independent validation.

## One simple next position experiment

Use the pair differences to **initialize the existing relative receiver clocks**,
then run the unchanged B7 position model. This addresses a physically plausible
receiver nuisance failure without introducing satellite-specific correction terms.
It should be a separately frozen experiment after reviewing the complete90 report.

From the fitted-B7 endpoint and its shared pairs, form the existing nuisance row
difference `D = X_RX1 − X_RX0`, using the same duplicate averaging. Include only
existing receiver affine/smooth-clock coefficients permitted by the frozen test;
retain the existing affine-null basis, clock regularization and parameter bounds.
Initially leave RF-time, static c, satellite timing and satellite-slope coordinates
unchanged so the experiment isolates relative-clock initialization.

Solve one small regularized weighted quadratic for a feasible coefficient update.
The regularization should be the actual B7 clock penalty on the updated state,
including its linear term around the starting clock, rather than an unpenalized
projection. Apply a deterministic active-set solve for bounded coordinates; retain
rank-deficient common-clock directions through a specified minimum-change convention.
Common receiver clock modes cancel in the pair equation and cannot be inferred
from pairs alone. No receiver anchor is selected by reference position or error.

Use that single frozen fitted-derived initialization policy in both arms, with
c=0 and RF-time locks applied according to the existing matched-arm contract.
Run the ordinary B7 fitter with exactly the same observation set, candidate bank,
priors and budgets as a same-start control that makes no clock update. Preserve
both original B7 endpoints. Accept a new operational candidate only if independently
qualified and selected by the **unchanged comparable B7 objective**; retain failures
and ties deterministically. No per-scan choice between projection backgrounds or
error-selected initialization is permitted.

This proposal is an initialization experiment, not a claim that a pair-only solve
optimizes the full circular mixture likelihood. Re-evaluate the exact likelihood
and its convergence gate after fitting. Measure full DS16/17/18 coverage, mean/
median/p95/worst position error, paired regressions, fallbacks, frequency fit and
extra computation separately. Use matched c arms and disclose fitted-derived
conditioning. A second, equal-compute control can distinguish a useful clock start
from merely receiving another fit/recenter opportunity.

The prior embedded recommendation to profile linear clock blocks remains compatible:
this one-step initialization provides a small, understandable first test before a
more involved variable-projection optimizer. It has **no measured position benefit
yet**, and cannot establish the0.4km goal or justify automatic deployment. Freeze a
globally selected policy before randomized independent whole-recording validation.
