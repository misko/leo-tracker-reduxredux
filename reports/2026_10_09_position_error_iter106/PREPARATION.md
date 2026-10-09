# After calibration recovery: a small test of ordinary sub-kilometre accuracy

**Preparation only.** This note reads existing consumed-development reports and
current numerical source. It launches no fit, residual calculation, reserve
inspection or RF collection, and changes no production or frozen source.

The first accuracy experiment I would run after recovery is a **single global
frequency-width change from 125 Hz to 100 Hz**, against a same-start 125 Hz B7 control.
It adds no coefficients, no search regions and essentially no per-evaluation
cost. This is a falsifiable test of an existing likelihood assumption, not a
claim that the measurement noise is 100 Hz or that a common geographic bias has
been established. Two alternatives below are worth investigating, but require
more evidence or implementation before an accuracy comparison.

## What the existing evidence establishes

The [full B7 qualification](../2026_10_09_position_error_iter85/RESULTS.md) and
[reproduced control](../2026_10_09_position_error_iter86/RESULTS.md) include all 148
DS16/17/18 members. Fitted-c median error is 0.863677 km; dataset means are 0.979007,
0.819111 and 2.691656 km. DS18 contains a 53.400741 km failure. Descriptively removing
that one case leaves about 0.963 km over 147 cases, but **that is not an exclusion
policy or a replacement benchmark**. Recovering large failures alone cannot
establish the 0.4 km goal.

These are error magnitudes. They do not establish that errors share one signed
east/north offset, nor that an RF hardware defect caused them. A post-fit vector
error plot may describe directional bias, but reference coordinates cannot
define a correction, choose a hyperparameter per scan, or select an operational
winner. Candidate positions used to compute satellite geometry are legitimate
inference variables and are different from reference coordinates.

The [full B7 residual audit](../2026_10_09_position_error_iter87/RESULTS.md)
reconstructed both c arms on every member. Median per-recording fitted-c RMS is
61.719 Hz, compared with 123.995 Hz for c=0, while the deployed Gaussian frequency
width is 125 Hz. Median adjacent residual correlation remains 0.261 fitted-c and
0.363 c=0. These are conditional, fitted and assignment-selected residuals;
neither their RMS nor their correlation is an unbiased noise calibration.

The [paired-clock projection audit](../2026_10_09_position_error_iter90/RESULTS.md)
weakens the case for adding receiver-by-satellite offsets. Median per-recording
mean absolute fitted-c pair contrast goes 23.944→8.849→5.583→1.874 Hz through
unadjusted shrinkage, linear-background projection and existing B7 smooth-clock
projection. That is evidence of confounding, not proof that regularized B7 can
freely absorb those effects. A receiver-antisymmetric correction also leaves
common spatial information unchanged in the balanced known-assignment Gaussian
case; see the [synthetic geometry study](../2026_10_09_position_error_iter91/README.md).
I would not make that extension the next ordinary-accuracy experiment.

## Three candidates, in priority order

### 1. One globally narrower frequency likelihood: 125 Hz versus 100 Hz

The current [likelihood](../../src/leo/analysis/hard60_score.py) uses one Gaussian
width for all observations and satellite candidates, with its normalization,
visibility and clutter mixture retained. Change only `score.sigma_hz` to 100.
This is the frequency width in **Hz**: it is not the 2 s relative-timing prior,
the ±60 Hz/s receiver slope bound, or the 0.5 Hz/s satellite-slope prior.

With fixed assignments in the Gaussian limit, the frequency quadratic becomes
1.5625 times as strong relative to unchanged priors. The Gaussian density at zero
residual also rises by 1.25 times, which can change clutter/association weights.
Both effects are part of the actual model change; it would be incorrect to
describe this as merely turning up a residual penalty while leaving association
unchanged. No likelihood normalization may be dropped.

**Causal hypothesis:** a conservative frequency width can let timing/clock
regularization pull the ordinary solution away from the best supported common
geometry, and can retain weaker competing assignments. A modest globally fixed
change could improve that balance. **Counter-hypothesis:** the width protects
against TLE/model error and correlated residuals; narrowing it could overfit,
discard valid windows as clutter or destabilize assignments and worsen position.
The low in-sample RMS alone does not decide between these explanations.

100 Hz is one predeclared 20% perturbation, not a fitted hardware estimate and not
a value selected separately for different scans. I found no explicit 125→100 Hz
frequency-width ablation in the reviewed iteration reports; the many previous
sigma studies changed timing, clock or satellite-slope priors. This is a bounded
literature-of-the-repository observation, not a claim to exhaustive novelty.

Implementation is a small research model-construction change: replace the base
score before constructing the same B7 `SlopePrior` model. Keep the exact same
bank, observation rows, clock-node layout, satellite centers and physical/clock
start. No new nuisance block or finite-difference geometry is required.

### 2. One temporal-correlation state per orbit-blind tracklet

The residual correlations surviving B7 justify asking whether independent
windows overstate information. A lean candidate is a scalar exponentially
correlated residual state, propagated with `a_i=exp(-dt_i/tau)`, plus independent
measurement noise. Conditional on known assignments, a one-dimensional Kalman
innovation recursion evaluates the Gaussian likelihood in linear time, with
innovation variance and log normalization retained. Zero correlated variance
must exactly recover the independent Gaussian model.

This is **not** inverse-count reweighting. However, the deployed likelihood is
a clutter-plus-satellite mixture, not a known-assignment Gaussian track. A
hard-assigned Kalman score or a Gaussian state approximation is an additional
model assumption and must be named and tested; it must not be presented as the
exact current mixture likelihood. Orbit-blind tracklet membership, gap handling
and all correlation parameters must be fixed without reference locations.

Before position fits, require positive out-of-block predictive gain for residual
innovations after accounting for existing clock/time structure. Estimate any
global covariance parameters only on predeclared training recording groups,
then freeze them. The descriptive 0.261 correlation does not establish a causal
stationary process or justify a numerical tau. This mechanism was already
proposed in [iteration 86 ](../2026_10_09_position_error_iter86/NEXT_MODELS.md);
the later 148-member audit strengthens its motivation, not its validation status.

### 3. A parameter-free receive/emission-time consistency correction

The inspected [orbit scorer](../../src/leo/analysis/regional_position_score.py)
and [native kernel](../../src/leo/analysis/_regional_orbits.cpp) interpolate a
satellite state at receive-time plus its fitted orbit shift and use radial
velocity there. No explicit light-travel-time iteration appears in these scoring
functions. This is a source-level question to audit across the full propagation
path before declaring an omitted physical correction.

Under a vacuum propagation model, emission time satisfies
`t_emit=t_receive-range(t_emit,t_receive)/c_light`. A consistent calculation
must also express emitter and receiver states in compatible inertial/rotating
frames and differentiate with respect to receive time. Simply subtracting
`range/c_light` from an ECEF interpolation argument is not a complete treatment.
This propagation speed is **not** the fitted RF calibration coefficient named c.

The attractive feature is no learned parameter. The limitation is that existing
per-satellite timing shifts and slopes may absorb nearly all of its effect.
First calculate its prediction change at ordinary hypothesis positions and
project it against the existing timing/clock/slope derivative span. If the
remaining component is negligible, do not run an expensive position study or
promise hundreds of metres of improvement. No magnitude or accuracy benefit
has been measured here. Consistent frame/time derivatives and a synthetic
moving-emitter oracle are prerequisites, so this ranks behind the width test.

## Prior negative experiments constrain the next protocol

| Previous change | Observed result | Consequence |
|---|---|---|
| [Inverse-count density weighting, iteration 17 ](../2026_10_08_position_error_iter17/README.md) |107-member fitted-c mean 1.004952→1.012704/1.025073 km; worst 2.835→4.122/4.285 km |Do not normalize windows by sampling density and call it calibrated uncertainty.|
| [Satellite-slope sigma 1 Hz/s, iteration 25 ](../2026_10_08_position_error_iter25/README.md) |119-member mean 1.001464→0.953968 km, but worst 2.763→3.905 km and two newer cohorts regress |Better mean or frequency fit alone does not justify more freedom.|
| [Geometry-protected slope prior, iteration 86 ](../2026_10_09_position_error_iter86/RESULTS.md) |148-member mean 1.317354→1.327178 km; median 0.863677→0.883465 km |Protecting local geometry derivative modes was not automatically beneficial.|
| [Paired contrast projection, iteration 90 ](../2026_10_09_position_error_iter90/RESULTS.md) |Most contrast shrinks after projecting existing clock span; no new position fit |Do not label receiver differences a measured satellite/LNB bias.|

The [controlled B7 effects](../2026_10_09_position_error_iter85/CONTROLLED_EFFECTS.md)
also separate search recovery from ordinary improvements: search-only changes
improved only 2/148 fitted-c cases, whereas joint clocks improved 104/148. The
sub-kilometre effort must examine a model assumption across the whole corpus,
not keep choosing individual bad scans or repeatedly widening slope priors.

## Preferred falsifiable protocol: fixed 100 Hz against a 125 Hz refit

This is preparation: the numerical protocol has not been frozen or executed.

1. **Freeze membership and starting method.** Use all 63 DS16 members, 51 DS17 members
   and 34 DS18 members. Preserve DS16 original 48/added 15 and DS18 prior 24/other 10
   exposure labels. All 148 are consumed development. Use sealed B7 endpoints
   unless a separately qualified generic recovery policy has first been adopted
   uniformly as the research baseline; never mix improved single-case states
   into selected rows. Add newer development only when every member's matched
   B7 source is established; older hard60 results are not interchangeable.
2. **Four matched fits per member:** 125 Hz control and 100 Hz candidate, each fitted-c
   and c=0. Every fit gets the same fitted-derived physical/clock start, bank,
   observations and 90 s/600 budget. Keep relative timing 2 s, receiver hard60,
   satellite slope 0.5 Hz/s and all other B7 priors unchanged. c=0 locks both static
   RF stretch and RF-time terms. Disclose the shared fitted-derived starts as a
   conditional c ablation. No extra region search, restart or new candidate-only
   qualification rescue in this model test.
3. **Required numerical controls.** Reconstruct 125 Hz archived objectives within
   the existing `1e-6` tolerance before fitting. The same-score control constructor
   must exactly nest B7; test mixture normalization and physical/clock gradients
   at both widths, wrapped-frequency invariance, c=0 locks and equal observation
   membership. No reference coordinate reaches model construction or fitting.
4. **Qualification and fallbacks.** Retain the unchanged independent physical/KKT
   gate. An unqualified 100 Hz result falls back to its matched qualified 125 Hz
   control, then the archived same-arm B7 endpoint. Preserve raw failures.
   Never compare 125 Hz versus 100 Hz objective values to pick a scan's winner.
   The candidate is one global rule; there is no per-scan best-error selection.
5. **Report mechanisms separately.** Position mean/median/p 95/worst and paired
   regressions, by dataset and pooled, are primary. Also report unweighted
   frequency RMS under each fitted prediction, signal/clutter responsibilities,
   assignment changes, nuisance norms, timing penalties, active constraints,
   raw convergence/fallbacks and runtime. A lower Gaussian width, lower RMS or
   lower model-specific score does not itself count as better position accuracy.
6. **Predeclared development decision.** A useful first-step candidate should
   improve both pooled mean and median by at least 5%, with no dataset mean
   worsening over 5%, no pooled p 95/worst worsening over 10%, and no increase in
   cases whose paired error regresses by more than 1 km relative to the same
   archived B7 endpoint (compare this count for candidate and control). Count missing inputs and
   numerical failures explicitly. These proposed thresholds must be frozen
   before outcomes; they are not proof of achieving the 0.4 km goal. If they fail,
   retain 125 Hz rather than tune another width against the same plotted failures.
7. **Grouping and validation.** Freeze randomized whole-recording groups, joining
   shared-session/IQ dependencies and predeclared adjacent-time blocks, stratified
   by dataset/sample rate where possible. Keep both receivers together. This
   fixed-width test has no learned training parameters; groups measure stability
   and support paired uncertainty estimates, not an independence claim for
   repeatedly inspected data. Any later covariance calibration must use training
   groups only. Leave all reserves closed until one global policy and genuinely
   independent validation protocol are separately approved and frozen.

This experiment can falsify a cheap uncertainty assumption. It cannot by itself
identify a physical source of bias, certify performance at a new geographic
site, or justify a deployment from an attractive few examples.
