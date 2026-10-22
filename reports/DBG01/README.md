# DBG01 — standard localization debug analysis and figures

DBG01 is the reusable diagnostic procedure for a named dataset, scan and
algorithm version. It documents **why a position estimate or missing track
occurs**, without silently changing the benchmark algorithm. The first complete
example is [ALGO01 on DS23-0217](../2026_10_18_algo01_ds23_0217/README.md).
Versioned specifications are [ALGO01](../ALGO01/README.md) and
[ALGO02](../ALGO02/README.md). The completed
[ALGO02 evaluation on all 413 DS23 recordings](../2026_10_19_algo02_ds23_full/README.md)
includes the matched fresh baseline, all outliers/failures and source/causal audits.
Name the algorithm version explicitly; a diagnostic does not change its benchmark.

An instruction such as **“Run DBG01 on DS23-0217 with ALGO01”** means perform
the analysis below and deliver the standard figures, machine-readable evidence
and a Markdown explanation. State omissions or unavailable inputs explicitly.
DBG01 is a diagnostic specification, not a new estimator or a claim that the
current case-specific scripts are already a generic production API.

## 1. Freeze and replay the case

Record dataset/recording identity, scan cutoff and UTC anchor, algorithm/source
hashes, graph and noise configuration, input authority hashes, candidate-bank
contents, selected RF nomination branch, aliases, calibration masks, parameter
priors and numerical budgets. Preserve original benchmark inputs and outputs.

Replay the saved endpoint objective and residuals before explaining it.
Default replay tolerance is absolute loss difference below1e−5; record actual
differences. Keep measured GLRT CFO unchanged modulo integer alias periods.
Count unique physical observation identities, distinguishing original winners,
additional resolved peaks, alias replicas and interpolated plot samples.

Only pre-observation TLE epochs **and collection timestamps** are eligible.
Use genuine earlier epochs separated by at least1second for ALGO01's causal
phase uncertainty. Record missing-history fallbacks. No following TLE, true
satellite list or GPS-selected branch enters inference.

Use the declared regional box unchanged. The current ALGO01 default is a
**25×25 km square centered at37.906,−122.545**. GPS is used for evaluation and
explicitly labeled oracle diagnostics only. If a scan has another declared
region or reference, record that configuration rather than inheriting this
example's coordinates.

## 2. Standard figures

Every figure identifies scan, algorithm version, c arm, evidence denominator,
position/association conditioning and any display-only frequency transform.

### A. Associated GLRT and tracks — `associated_GLRT.png`

Use one panel per RX/channel, native measured CFO Hz or kHz against device-time
seconds. Gray shows all winning GLRT observations. Color accepted observations
and graph/piecewise-polynomial tracks by satellite hypothesis, retaining track
IDs in a companion table. Show all receivers/channels, not only successes.
Do not display a polynomial prediction as an observed measurement.

### B. Unassociated GLRT and tracks — `unassociated_GLRT.png`

Use the same panels and axes. Gray shows all observations; red shows
unassociated GLRT marks; lines colored by track show unassociated graph
polynomials. Use exact accepted observation IDs, including partial masks:
an accepted suffix must not turn its rejected prefix gray by track-key alone.

Break down unassociated points into (i) graph-owned but satellite-unassociated,
(ii) outside graph tracks, and (iii) ambiguous/secondary evidence if available.
Provide per-track point count, duration and active-curvature eligibility.
Unassociated does not mean noise. A failure of the existing graph to recover a
curve is not proof that no physical curve is present.

### C. Residual overview — `track_residuals.png`

Plot satellite residual RMS against duration, sized by point count and colored
by gate status; include the RMS threshold. Provide mean, slope, quadratic/BIC,
step, autocorrelation, maximum independent-radio-standardized residual, alias,
visibility and multi-owner support diagnostics where applicable. Distinguish
polynomial residual checks from satellite residual checks.

### D. Loss and gradient — `loss_gradient_10km.png`

Default upper panels sample a **1 km grid in a10 km radius** around the regional
center. Default lower panels sample a **0.25 km grid over±2 km** around the
supplied true site, explicitly labeled as an evaluation-centered zoom. Clip all
evaluations to the original search box and disclose any clipped area.

At each pixel retain the same observed calibration points, satellite labels
and alias integers, and refit nuisance coefficients and robust noise variables.
For ALGO01, perform five absolute-prior phase-reference refreshes at that fixed
position. Persist pixel scores, RMS and final reference changes. This is a
**conditional phase-profiled loss surface**, not a full acquisition/graph/
association pipeline run at every pixel and not a normalized probability map.

Plot loss relative to the saved RF-selected endpoint, mark the true site and
endpoint, and overlay normalized negative-gradient directions. Explicitly
state if arrow length encodes direction only. Also report actual 50 m central
difference gradients at the true site and endpoint in loss/km. Do not imply
that an off-panel endpoint appears within a local zoom.

### E. Regional restart convergence — `convergence_10km.png`

Default starts are all **81 points on a2 km grid inside the same10 km disk**.
Mark and label every start, actual accepted position iterates, phase-round
boundaries when useful, and final endpoints. Persist a start/endpoint CSV.
Lines must represent recorded solver steps; label any mere displacement arrows
as such. Report endpoint spread, branch switches, numerical stop reasons,
gradients and phase convergence, not only geographic error.

Enable satellite/alias branch reselection using a declared same-scan causal RF
hypothesis pool. For the current implementation, build the pool from **13 cold
RF discoveries on a5 km grid**, plus the original RF branches; deduplicate
identities/aliases and discard learned positions, phases and receiver state.
Use only discrete nomination hypotheses as shared proposals. Rescore the
finite pool after each accepted c=0 position step. Clearly disclose that this
does not exhaust arbitrary satellite combinations or rescreen every TLE at
every trial. Record whether changes were allowed and whether any occurred.

For the c ablation, use the c=0-selected branch schedule for fitted c so each
pair has matched final identities, aliases, observations and other priors.
Label this policy; fitted c does not get a separate GPS-selected branch.
If instead running completely independent discovery at each of81starts, label
that separate experiment and do not conflate its paths with shared-pool runs.

### F. Influence and controls — `influence_and_controls.png`

Refit after removing each satellite family and each curved track individually,
in both c arms. Preserve the original nuisance-prior design for controlled
influence comparisons; disclose this rather than silently changing orbital
support. Never rank raw scores from different observation masks. Report
geographic error/endpoint shifts as diagnostics, not a GPS-based rejection rule.

Use a declared small set of generic prior/noise sensitivities, with matched
observations, candidate sets, starts and search budgets. The initial ALGO01
set is baseline, phase floor3s, doubled causal phase widths capped at15s,
fragment-constant prior300Hz, receiver mean-drift prior1Hz/s, physical orbit
modes×3, and the existing150Hz/10s correlated-noise control. These are
sensitivities, not automatically recommended settings. Subsequent mechanisms
must be recorded as follow-up experiments, not relabeled as predeclared.

### G. Objective decomposition — `loss_decomposition.png`

Compare the fitted endpoint with a fixed true-site fit that re-estimates
nuisances and phases. Report RMS, weighted data quadratic, nuisance-prior
blocks, grouped-noise/Gamma terms, integrated log-volume and visibility terms.
Verify that differences add to the actual objective difference. Keep full
normalizations when comparing different noise models.

Locating a preference in a loss component does not establish an implementation
defect. For example, a dominant Gamma-term difference motivates a fixed-noise
precision ablation, not an immediate decision to remove robust inference.
Separate frequency-fit improvements from position accuracy.

## 3. Mandatory targeted review of an obvious missing curve

When the user or a figure identifies a visible curve, trace it through **each
stage** before calling it clutter or a polynomial failure:

1. Plot a native-CFO zoom with original winning GLRT marks, every available
   gate-passing candidate rank, current track ownership and the requested time
   interval. Use device counters plus within-visit probe offsets; verify these
   reproduce the persisted observation times.
2. Distinguish loss before graph discovery (one-winner filtering), lack of a
   graph path, polynomial/support rejection, ownership arbitration, common
   finalization, calibration ineligibility and satellite-association rejection.
3. Instrument graph paths, scores, point counts, gaps and minimum edge cadence.
   Check cadence assumptions against the actual probe stride. Trace the first
   failed condition numerically; later gates were not reached if no path was
   proposed. Inspect both the full lane and the unresolved subset.
4. For a proposed curve, compare supported polynomial degrees on identical
   observations under frozen radio noise and complexity penalties. Do not
   remove a boundary point or raise a threshold merely to pass a plot.
5. If one-winner filtering obscures simultaneous signals, reopen the already
   archived GLRT candidates. Deduplicate alias/peak replicas per probe, retain
   resolved signals separately, and enforce unique peak ownership and at most
   one peak per physical track/probe. Report original-winner coverage separately
   from additional peaks. Do not silently change benchmark denominators.
6. Label restricted-window fits, altered discovery thresholds or alternative
   graph proposals as diagnostics. Successful recovery still needs independent
   calibration, active curvature and satellite gates before voting on position.

If a change is proposed, test its causal mechanism against a matched control,
add component-owned tests for implementation changes, and propagate it to
position before claiming better localization. Preserve the original benchmark.

## 4. Standard report contents and conclusions

Deliver a `README.md` with all figures and tables, input/source hashes, exact
commands/configuration, machine-readable memberships and scores, per-start CSV,
interventions CSV, and `validation.json`. Minimum summary:

| Topic | Required values |
|---|---|
| Evidence | All GLRT, graph-owned, associated, unassociated, calibration points/tracks |
| Position | c=0/fitted-c error, endpoint, regional box and actual initialization |
| Stability | Start count, endpoint spread, modes/switches, stop reasons and gradients |
| True-site diagnostic | Profiled loss gap, RMS, passing gates, gradient and decomposition |
| Influence | All single-family/track effects; no GPS-picked production deletion |
| Approximation | Phase convergence; exact joint-SGP4 versus tangent where available |
| Missing curve | Exact loss stage, failed threshold/value, candidate-rank/cadence evidence |
| Uncertainty | Supported conclusions, unresolved physical causes and scope limits |

A stationary endpoint or agreement across starts does not certify the true
position. Passing residual gates does not certify satellite identity or
unbiased location information. Local Hessian scales are not validated
confidence intervals. State the strongest supported explanation and what
remains unresolved; distinguish an optimizer failure, a conditional model
minimum and an exhausted identity search.

## 5. Current implementation and example artifacts

The current case-specific implementation is
[investigate_algo01_ds23_0217.py](source_snapshot/tools/investigate_algo01_ds23_0217.py),
with [reporting/figures](source_snapshot/tools/report_algo01_ds23_0217.py) and
[owned tests](source_snapshot/tests/analysis/test_algo01_0217_tool.py). Adapt case/input
bindings explicitly for another scan; do not assume editing a directory name
alone changes all imported case bindings.

Use the repository `.venv`, `PYTHONPATH=src:tools`,
`OPENBLAS_NUM_THREADS=1`, `OMP_NUM_THREADS=1`, and bounded subprocess workers.
No new RF collection is part of DBG01. QNAP inputs remain read-only.

The archived [source-overlay instructions](source_snapshot/README.md) explain
how to combine these additions with ALGO01's frozen source tree in an isolated
replay workspace. Snapshot files are evidence, not a runtime dependency.

The [RX1 CH1 missing-fragment example](../2026_10_18_algo01_ds23_0217_rx1_ch1_tail/README.md)
demonstrates the mandatory visible-curve audit, including an exact graph replay,
candidate-rank inspection, polynomial residual zoom and threshold evidence.
The [scan-217 improvement experiments](../2026_10_18_algo01_0217_improvements/README.md)
extend the example with confidence weights, receiver/channel residual transfer,
simultaneous whole-family replacements and exclusive secondary-peak recovery.

Example execution order: `prepare` figure/surface request; explicit diagnostic
`audit`; `discover` indices0–12; `bank`; `restart` indices0–80; `grid` chunks0–7;
`family` and `track` interventions; declared `prior` controls; reporting
`surfaces`, `restarts`, `details`; final source/link/provenance validation.
GPS-centered diagnostics must be labeled and kept separate from inference.

Example figures:

![Unassociated GLRT](../2026_10_18_algo01_ds23_0217/unassociated_GLRT.png)

![Loss and gradient](../2026_10_18_algo01_ds23_0217/loss_gradient_10km.png)

![Regional restart convergence](../2026_10_18_algo01_ds23_0217/convergence_10km.png)

## 6. Diagnostic addendum, 2026-10-19 UTC

The [DS23 uncertainty study](../2026_10_19_ds23_uncertainty_study/README.md)
adds the following controls for subsequent DBG01 investigations. They supplement
the published figures above; they do not replace the original frozen examples.

Report the recorded UTC anchor and its complete host bracket. A midpoint is an
estimate, not exact sample UTC. For a clock sensitivity control, shift one shared
UTC value inside those recorded bounds, query ECEF geometry at the shifted UTC,
and keep elapsed device times unchanged for receiver drift/smooth corrections.
Freeze the TLE cutoff at the original earliest bound. Keep satellite phase
adjustments separate from UTC, and hold data/labels/aliases fixed across the
clock grid. Report both RF loss and position effects. A boundary optimum on a
nearly flat profile does not identify a precise clock correction.

When nuisance uncertainty could explain the error, report local Schur position
information and oracle controls freezing receiver, satellite phase/orbit and
fragment terms at their fitted values. State which noise/prior precisions are
conditioned on, check derivative steps, and label these as local generalized
widths. They are not new position estimates, calibrated coverage or a fundamental
CRLB. Do not infer that reducing an oracle width is an available algorithmic fix.

If an identity decision appears driven by the approximate integrated objective,
an optional fixed-position importance audit can test its approximation gap.
Preserve the same data, prior and normalization, and report sample count,
effective sample size and Monte Carlo uncertainty. Poor sampling is inconclusive.
Keep a c0-only objective audit separate from paired-c localization comparisons.

## 7. Confidence and evidence addendum, 2026-10-19 UTC

The [association-evidence study](../2026_10_19_ds23_association_evidence/README.md)
adds fixed-observation confidence ablations, broader simultaneous family changes
and secondary-peak recovery. Keep the original retained mask for soft weighting
comparisons; report hard confidence selection separately. An invalid trial must
stay in the denominator with an explicit failure/fallback rule. Conditional
identity scores are not calibrated correctness probabilities. Do not compare
generalized losses with different observation powers as model evidence.

Compare residuals across all same/different receiver, band and satellite-family
strata using unique matched physical observations. State available bands and
pair counts. Residuals conditioned on the joint fit can reveal remaining shared
structure but cannot prove that a receiver or orbit caused the position bias.
Illustrate a family observed on both receivers; do not select only striking
examples by eye or pool dependent track pairs as independent significance tests.

For joint identity debugging, include changes to several complete families and
retain alternatives that fail in isolation. Record the finite beam, proposal
anchors, candidate catalogue, optimization budgets and all failed attempts.
Distinguish cheap proposal fits from fully refined paired finalists. A finalist
must improve the same normalized radio objective and satisfy the original
physical gates; being geographically closer to the reference is not a selection
criterion. A radio-preferred replacement can still increase position error.

For secondary peaks, preserve the public adapter's canonical physical-probe ID
and time authority for each recording format. Match that identity set against
the frozen winning observations before recovery. Use at most one selected peak
per probe and each chosen peak's own radio-noise estimate. Exclude incumbent
calibration and already-associated output points when claiming new evidence.
Test new curves individually before joint addition; retain all original points.
Report local model-conditional information separately from actual position error.

The [curvature/shape study](../2026_10_19_ds23_curvature_shape_study/README.md)
also distinguishes statistically supported weaker curvature from a fixed
amplitude threshold. A higher polynomial degree alone is insufficient. Report
noise-weighted departure from affine, a complexity penalty and residual screens.
New calibration points may already have been associated as output tracks and
must not be counted again as association gains.

## 8. Predictive calibration and measurement controls, 2026-10-19 UTC

The [clock/measurement report](../2026_10_19_ds23_clock_measurement_controls/README.md)
adds reciprocal receiver/family prediction. Omit one satellite family's curves
on one RX while retaining its opposite-RX evidence and other satellite families.
Refit position from the regional center and calibration from training data only.
Predict the omitted full CFO vector with position/nuisance uncertainty; do not
refit omitted fragment constants or group noise. State that frozen identities,
alias integers and radio-noise proxies make this a conditional calibration
test, not independent blind satellite identification. Restore all original
points for the final matched c=0/fitted-c comparison. Do not accept more receiver
freedom merely because the in-sample residual decreases.

Before adopting an apparent time-tag correction, use matched opposite chirps
with the same known pilot envelope and phase. Separate CFO-versus-chirp response
from off-grid static CFO bias and retain peak-selection switches as exceptions.
A local sensitivity is not always a physically meaningful measurement instant.

For native measurement qualification, pin binary and build-receipt hashes and
distinguish that proof from identity of the actual capture binary. Test physical
delay/Doppler, independent code/carrier rates and off-grid frequency cases.
The tested500Hz FFT/magnitude-parabola interpolator has a template-predictable
noise-free bias; a mathematical inverse validated on those cases is not yet a
qualified noisy-data correction. Canonical GLRT CFO must be used before alias
lifting, since the frequency alias period is not an integer multiple of500Hz.
Keep the original persisted GLRT contract immutable and GPS outside calibration.

For bounded archived-IQ qualification, see the [seven-curve refinement study](../2026_10_19_ds23_raw_pilot_refinement/README.md). Select complete original curves using radio-only criteria, preserve every selected observation, verify declared manifests and window hashes through the public read port, and retain unresolved score replays. Compare fixed-epoch and joint carrier/epoch/code-rate fits using the degree selected on the original CFO. Record search boundaries, exact/control margins, odd/even frame behavior and effective times. Report boundary-inclusive radio diagnostics separately from boundary-fallback position trials. Update canonical CFO by observation ID while preserving integer aliases; leave unrefined points and the original persisted contracts unchanged. Independently report matched c=0/fitted-c position error: the large RX2 RMS reduction in these two diagnostic scans gives only a small position change under the old uncertainty law. Do not treat a lower polynomial residual or experimental native-library replay as proof of an unbiased measurement or the identity of the capture binary.

The [precision/family-reentry controls](../2026_10_19_ds23_refined_precision/README.md) show why every point-level intervention needs exact active-ID intersections. A cleaner curve can be entirely masked. Distinguish conditional residual rejection from the independent-owner cascade: eccentricity fixed scan 202's residual gate, but a second original channel companion was required for family support. Reconsider whole originally accepted companions with matched c arms, retain all incumbent points, and preserve failures rather than weaken a gate. Restore below-40Hz uncertainty only in an explicit research model with consistent normalization and unchanged noise for every other observation. Compare complexity by normalized RF evidence on the same observations; do not choose the more accurate GPS endpoint when RF prefers the simpler model. Report that legacy 75Hz floors may be insensitive to structure at newly measured 10Hz precision.

After restoring previously masked observations or changing their precision, repeat broad causal identity competition; the old masked-data ranking is insufficient. The [scan-202 follow-up](../2026_10_19_ds23_refined_catalogue/README.md) uses a shared phase across family curves, all-catalogue proposal screening and matched full physical fits. It reverses an apparent fixed-identity position gain. Report the closest geographic candidate even when RF rejects it, but never select it using GPS. Separate legacy gates from precision-scaled conditional diagnostics. For a loss map, identify actual samples, box/radius clipping, fixed identities and nuisance-refresh rounds; mark gradient arrows as directions with arbitrary display length, not descent trajectories. At the known site and RF endpoint, decompose the normalized objective exactly and compare finite-difference gradients at two step sizes before attributing bias to an optimizer stall or one satellite.

## 9. Dense measurement and uncertainty-consistent gates, 2026-10-19 UTC

The [dense RX2 and causal-shape report](../2026_10_19_ds23_dense_rx2_and_causal_shape/README.md)
keeps every original active calibration point. Recompute radio-only noise from
local measured-CFO scatter rather than treating a whole-polynomial PRESS error
as measurement variance. Report leverage, original masked-ID intersections,
whole-curve prediction error, local scatter, split-frame floor and boundary
fallbacks separately. A tail already excluded from calibration can still
distort whole-curve noise learning. Never hide that by deleting active points
or learning noise from satellite/GPS residuals.

With heterogeneous pointwise sigmas, evaluate GLS profile residuals and weighted
mean/slope/step tests, quadratic structure and whitened correlation. Preserve
physical RMS/bias limits, aliases, visibility and independent-owner support.
Keep the old rejection and revised development outcome side by side. Require
uniform-noise parity, mixed-noise false-rejection controls and sensitivity to
real slopes/discontinuities before interpreting a gate change. Exact saved-fit
replay must show that no refit or observation deletion was used to pass it.
Passing a pooled structure gate does not certify iid Gaussian residuals;
illustrate individual large standardized residuals and noisy fallback prefixes.

Keep causal mean and covariance qualification separate: the signed full-state
forecast selected zero on scan 202, while a zero-mean Student diagonal shape
prior improved historical innovation density. A later historical TLE remains
a proxy, not true orbit error. Split by publication events and require RF-age
qualification before generalizing next-publication results. Report both c arms,
RF-ranked identity alternatives, unchanged denominators and actual position
accuracy. A six-identity inherited shortlist retest is not a fresh all-bank
rescreen under changed data. Update RX/band/family residual comparisons with
the same unique-time matching rules after measurement interventions; keep
conditional correlation distinct from causal attribution.

## 10. Calibration prediction does not establish localization accuracy

The [dense receiver-prediction study](../2026_10_19_ds23_dense_receiver_prediction/README.md)
extends reciprocal RX/family omission to up to three families per scan and
the original twenty-scan cohort. It demonstrates a useful local correction
on precise scan 202, but a worse fitted-c cohort median under the fixed rule.
Report calibration prediction, full-data frequency loss and geographic error
as separate outcomes, including cases where they disagree. Never choose the
GPS-favored covariance per scan or discard a regression from the denominator.

When predicting with an extended physical model, differentiate the complete
current feature design with posterior coefficients fixed. A base-class feature
builder can omit later-added physical columns even when the runtime prediction
method correctly includes them. Require an analytic expanded-design covariance
test. The actual scan-202 runtime orbit predictor was verified to include all
five physical coordinates; no prediction truncation was found.

State exactly what is held out. These folds omit target RX/family data from
position and nuisance fitting but condition on previously frozen identities,
aliases, support and radio-noise proxies. Local dense radio-noise proxies use
complete curves, including the omitted observations. This is not blind raw-IQ
validation or exact predictive integration. Record approximate position/Student
covariance, unfitted target constants/noise, family selection and dependence
between folds. Restore all original points before matched final c-arm fits.

## 11. Shared carrier priors and robust fragment contrasts

The [carrier study](../2026_10_19_ds23_shared_carrier_constants/README.md)
compares independent fragment constants, the old variance-preserving
correlation, and one RF-scaled satellite carrier plus Gaussian or Student
fragment deviations. Keep prior scales, actual marginal variances, phase priors,
point masks, physical support and c-arm budgets explicit. A shared carrier
prior can improve one precise scan while worsening the original cohort.
Preserve the negative control and every gate failure; do not select a prior
because its geographic endpoint is closer to the reference.

Verify compact covariance versus explicit shared/independent Gaussian columns,
including normalization under the grouped-noise likelihood. For robust
contrasts, test that an exceptional fragment can deviate without dragging all
others, and that wholly unobserved independent priors integrate to one.
Collapse unused Student priors rather than accumulating a gratuitous
Gaussian/Gamma variational gap. Preserve pilot source/results when correcting
the calculation and verify geometry and active predictions remain identical.
Interpret precision only on active fragments; it is not an identity probability.

Repeat identity competition when a prior or measurement changes materially.
Include the old RF shortlist and exact incumbent aliases, label fresh screen
anchors and covariance assumptions, and recompute phase means in each new
candidate's label order. Distinguish one-family full-catalogue screening from
global reassociation, splits and mergers. Shared carrier priors do not inherit
earlier receiver-prediction qualification automatically. Report both conditional
fixed-identity improvements and the result after RF identity ranking.

## 12. Qualify measurement changes across formats before interpreting position

The [RX2 measurement cohort](../2026_10_19_ds23_rx2_measurement_cohort/README.md)
extends direct known-pilot fitting beyond the initial fast-recording case.
Seal physical observation IDs and complete original curves before fitting.
Retain archived values and uncertainty at frequency, epoch or rate boundaries;
never remove those points to manufacture a cleaner residual distribution.
Keep measurement, effective-time and radio-noise interventions distinct. When
testing additional physical orbit directions, compare matched c arms and
integrate their priors and complexity rather than adding free polynomials.

Verify the read port against each recording's real coordinate conventions.
Fast tracking virtual sessions span separately named recording segments.
Native adaptive chunk visit indices address the retained stream: map through
the authenticated retained-visit list to recover original device events and
retune gaps. Payload offsets are not elapsed time. Check whole selected
adaptive chunks and selected fast windows against supplied authorities;
do not claim a final complete decoded fast-chunk digest after stopping its
iterator early. Exercise both 2.5 and 10 MHz through the real read paths.

Compare a faster optimizer to the reference on identical samples, templates,
parameter count and scout. Preserve slower pilot versions. Report optimizer
timing separately from full remeasurement, I/O and localization timing.
An increased projection score is not independent proof of a correct CFO.
Scoring at the persisted final CFO may fail to reproduce an archived score
when the acquisition CFO was not persisted; keep that provenance exception
separate from a hash/counter mismatch and do not select points by replay luck.

After precise measurement, audit both legacy and explicit pointwise-noise
residual gates. A small absolute RMS can retain significant slope or steps.
Do not trim original observations to rescue the new model. Preserve every
raw trial, paired failure, incumbent fallback and cohort regression. Recheck
phase-reference convergence before blaming a new optimum on insufficient
refreshes. Repeat bounded causal identity competition under the new data;
one-family screening is not global reassociation or identity certification.

If testing phase continuity between pilot frames, separate amplitude fading
from phase coherence, retain frame-rate aliases and compare fixed-support
random-phase controls. Do not force a globally coherent model because a few
probes support it. Phase diagnostics on the same IQ are not independent
measurements. Keep the supplied evaluation coordinate out of all measurement
and inference choices, and state the absence of per-recording survey authority.

## 13. Height geometry, frame timing and objective sensitivity

The [height/clock study](../2026_10_19_ds23_height_uncertainty/README.md)
tests a single shared antenna height with proper engineering priors, preserving
all curved measurements and existing physical nuisance priors. Recompute
elevation, range rate, phase derivatives and orbital features at each height
reference; subtract the derivative times that reference from the intercept
to preserve an absolute zero-mean prior. Include its Gaussian penalty and
integration determinant. A zero Gaussian feature must integrate to one.
Replay the complete physical mean at the posterior height before accepting
a linearization. Report local height/position covariance with fixed Gamma
precisions as an approximation, not surveyed altitude or calibrated coverage.

Frame-epoch diagnostics must use device counters plus within-visit offset and
the measured epoch. Form geometry at frame arrival, rather than the CFO's
effective time. Keep the frame-period ambiguity separate from CFO aliases.
Split gaps explicitly and test sensitivity to short-window boundaries without
claiming alignment with actual network reconfiguration. Record positive-range,
negative-range and free-curvature diagnostics on the same unwrapped support.
A synthetic sign test qualifies the calculation, not the archived capture
binary or transmitter clock. Negative measured coupling does not justify
reversing physical propagation delay or treating an apparent clock-steering
point as receiver position. No timing observation enters ALGO01 here.

Integration-volume gradients are local sensitivity diagnostics. They are not
optimization trajectories or evidence that removing a term improves accuracy.
Any profile-versus-marginal position experiment must first match observations,
aliases, priors, fixed noise/prior precisions and both c-arm budgets. Separate
the effect of freezing precisions from the effect of dropping log-volume.
Their different objective definitions cannot select a winner by raw score.

## 14. Conditional Gaussian marginal versus profile control

The [completed control](../2026_10_19_ds23_frozen_precision/README.md) freezes
the incumbent c0 noise/prior precisions and uses them in both c arms. Replay the
coefficient mean before fitting; insert a unit precision only at the ninth
hardware coordinate for fitted-c. Preserve absolute phase means, masks, aliases
and the cold regional start. Compare Q+logdet(A/P) with Q at common precisions;
do not rank their different costs as the same normalized probability. All twenty
scans pass, with a median 5.8 m actual endpoint movement. The earlier 154 m local
sensitivity used adaptive precisions and was not a refit. It cannot establish
that deleting the determinant corrects the position bias.

## 15. Linear evidence with curved-only calibration

The [linear predictive prototype](../2026_10_19_ds23_predictive_linear/README.md)
keeps linear data out of calibration normal equations, Gamma updates and owner
votes. At each horizontal position, fit curved data and predict added curves
with full covariance U_L A^-1 U_L', independent 300 Hz track constants and the
unseen Gamma inverse-precision mean of 2. Do not substitute independent pointwise
calibration errors for this shared covariance. Verify zero calibration-coefficient
change at the same position and exact canonical-ID disjointness. Freeze extension
labels/aliases from the c0 RF result and match them in fitted-c. A failure of an
original curved gate or a new linear gate causes paired fallback without trimming.
Report all twenty cases and distinguish additional predictive points from
calibration points. Saved failures and curves belong in the report alongside
position gains; the full cohort remains above the 0.5 km goal.

## 16. Robust predictive tails and conditional precision

The [robust predictive study](../2026_10_19_ds23_robust_predictive_linear/README.md)
matches marginal noise variance and bias variance to the Gaussian comparator.
Student tails still change central concentration and infer new-curve precision:
median precision is about 1.252 versus the Gaussian control's fixed 0.5. Thus
"robust" does not imply less position influence. Keep original curved calibration
means and precisions unchanged at a given coordinate, retain shared predictive
covariance, and report mean and median across every case, including fallback.
The new models improve scan 217 but worsen cohort median; do not promote them.

## 17. Coupled sample-clock frequency and time scale

An error epsilon in actual/nominal sample rate divides both carrier Hz and
elapsed time by 1+epsilon. Test the coupled physical column -F-t*F', separately
per receiver; do not equate it with an arbitrary RF-times-time drift. Include
current orbit corrections, receiver isolation, full prior normalization and
exact nonlinear geometry replay. Treat 25/100 ppm prior widths as engineering
hypotheses, not measured oscillator specifications. Two diagnostic scans retain
all original gates and show small position changes, not a demonstrated cause.

## 18. History-derived coordinates require current-scan evidence

A causal prefix spatial median uses earlier RF positions and assumes one site.
It is not an independent single-scan localization result. Test future-prefix
invariance and non-unique median conventions; do not use later scan results in
an earlier estimate. Replay calibration at each proposed coordinate with the
same current observations, labels, aliases and c-arm evidence. All twenty
individual-coordinate null replays pass; only fourteen prefix pairs pass.
After paired fallback the diagnostic is 0.794/0.513 km fitted-c, not its raw
0.507/0.431 km. Movement/reset handling and stationary-site confirmation remain
outstanding, and the full DS23 goal is unmet.

Preserve exact statistical failure margins. Examples include slope z=3.099,
step z=4.081 and quadratic BIC gain=10.0036. A companion's noise failure can
also trigger owner-support rejection. These cases motivate a noise-only audit
of the joint false-rejection rate across tracks and tests, including fitting
and group dependence. Do not simply loosen thresholds at geographically
favorable coordinates. Calibrate any new policy without evaluation GPS,
compare original and replacement policies on all scans, and retain physical
alias/visibility/bias bounds and genuine structured-residual failures.
Also test detection power against injected ramps, curvature and steps, including
receiver-common and satellite-common perturbations. Accepting a noise test does
not establish a satellite identity or absence of position bias.

## 19. Conditional family exclusion and full-population checks

Exclude every disputed family's curved point from calibration before testing
replacement identities. Keep its curved and predictive linear points in joint
prediction with shared phase/orbit uncertainty; linear points do not calibrate.
Restore all original observations and the original hierarchical priors for
final regional cold fits. Require unchanged gates and phase convergence in
both c=0 and fitted-c arms. Correct unused Student-coordinate variational gaps
only if no curved or predictive datum depends on the coordinate.

State whether position itself is excluded. The current family-cavity proposal
refits calibration at an endpoint originally estimated using the disputed
family. It accounts for conditional calibration covariance but does not
integrate position uncertainty. It is not a fully independent held-family
validation. Test joint position/calibration cavities or region-wide proposals
when the initial endpoint may restrict satellite nominations.

The October22 full410case comparison changes74scans under equal identity
priors: fitted-c mean/median1.498002/1.185452to1.469461/1.178102km;40improve,
34worsen. The number within0.5km stays48. Matched c0 mean/median improve
1.508507/1.249985to1.479378/1.190706km. Both formats improve in aggregate,
but1/3/6hour block-resampling intervals for fitted-c mean change include zero.
These are sensitivity intervals, not chronological holdouts or adoption rules.
All cases remain in evaluation. The0.5km goal and new-location validation
remain open.

Retain268's5.461to1.649km improvement and80's0.712to3.236km harm together as
diagnostic controls. Neither is a GPS-based selection rule. Passing residual
gates does not certify a transmitter ID or geographic correctness.

Use independent finite-orbit derivative checks with step convergence. A fixed
1e-3step had0.09776Hz truncation bias for a large candidate uncertainty basis;
Richardson extrapolation restored agreement under the unchanged2e-4Hz
residual tolerance. This repaired the audit, not the inference. All410nomination
and410position audits pass. Store per-case checkpoints with source-result,
execution and code hashes; failed checks prevent geographic evaluation.

The [full assessment](../2026_10_22_ds23_family_cavity_full_assessment/README.md)
includes every scan, matched c arms, uncertainty, harms, source snapshots,
numerical tests and proposed joint position/calibration experiments.

## Bounded worst-scan iterations and ALGO promotion

The current user instruction is to publish **every** bounded worst-N DBG01
iteration, including failures. This supersedes older positive-only publication
guidance. Use batches of two, preserve the full benchmark for ranking, and move
to the next worst scans when bounded tests stall. Reuse ALGO02/ALGO03; a debug
report is not a new ALGO release. New ALGO numbers require credible matched
full-DS23 improvements with both c arms, coverage, availability and regressions.

Aim for90% supported original GLRT association without forcing identities.
Separate points outside graph tracks from graph-owned association failures and
report graph-coverage ceilings. Gray is all original GLRT, red is unassociated
in unused panels. Plot persisted **Legendre** coefficients in the raw CFO gauge
using explicit physical observation IDs, with membership and alias gaps broken.

Propagate correlated receiver-calibration uncertainty when proposing unused
curves, especially on receivers with no retained curved calibration. A posterior
mean does not establish a precise correction. Exclude a proposed curve from
nomination calibration. Preserve ambiguity when predictive scores are close.
For newly activated families, count active passing receiver/channel owners when
authorizing orbital-shape coefficients; masked owners cannot justify extra
freedom. A phase-only control may recover evidence without relaxing gates.

[Iteration001](../2026_10_22_ds23_dbg01_iteration_001/README.md) records0081/0326:
97/21 recovered points, but large boundary errors remain. It includes loss maps,
81regional starts per scan, every active-family and curved-track ablation,
residual diagnostics and independent numerical audits. Following-TLE diagnostics
were explicitly omitted in this causal iteration. No new ALGO release or
full-DS23 gain is claimed. The next cases are0035/0041; the
[iteration index](../DS23_DEBUG_ITERATIONS.md) records the queue and policy.

## Iteration 002 additions: current labels, family alternatives and utilization

Bind diagnostic base rows to the **current** assignment node before selecting
family ablations or protected orbital support. A cached base object may retain
labels from before a family replacement even when the final fitter is correct.
Check measurement ordering/masks and null objectives; preserve initial requests
and record the correction. The iteration002 grouping correction leaves both
incumbent objectives and nomination scores unchanged.

Record **GLRT associated** separately from **GLRT used in position**, alongside
curved and predictive counts. An already associated curved track may remain
outside the fitting mask. A bounded promotion test must preserve its identity,
alias and original gates; linear tracks must remain predictive evidence.

Keep common alternative satellite candidates through family-level testing.
Combining only each curve's leading nominee can omit a valid joint original
nominee. Compare alternatives on the same observation mask with normalized RF
evidence, and never choose an ID using geographic error. A shared leading ID
also does not justify merging incompatible phases: 0035's 99-point 68060 union
is rejected with a 5.4–5.6 kHz long-track residual.

[Iteration002](../2026_10_22_ds23_dbg01_iteration_002/README.md) includes all
family/track ablations, 81 regional starts per scan, 27 figures, causal/following
TLE diagnostics, 472 independently replayed DBG01 endpoint arms, candidate
density checks and 15 tests. Following TLEs remain diagnostic only. Conditional
recovery improves 0035/0041 fitted-c errors to 3.741/2.835 km, but no full-DS23
gain or new ALGO release is claimed. Close this batch; next debug 0111/0390.
0405 stays in evaluation and is skipped only in this queue after its prior
bounded tests.

## Growth can pass residual gates while worsening localization

[Iteration 003](../2026_10_22_ds23_dbg01_iteration_003/README.md) closes
0111/0390 with all-family and all-retained-curved-track ablations, conditional
maps and finite-bank regional restarts. Adding an 18-point curved fragment
improves 0111 from 4.556 to 2.422 km fitted-c error. A coherent 43-point 0390
continuation passes the original gates yet worsens 4.255 to 6.725 km. A bad
join or incorrect identity is not established by that regression. Same-family
agreement can coexist with shared calibration/phase/position bias.

Report both association and likelihood utilization by c arm. 0390's expanded
fitted-c result associates584 points, but only566 enter position; its c=0 arm
associates566. No original accepted ID is lost. Neither scan can reach90%
within its current graph: ceilings are81.20% and77.85%. Counterfactual existing
physical orbit modes and diagnostic following TLEs do not remove the remaining
long-curve structure; neither relaxes final gates or enters causal inference.

The iteration prototypes a **research-only family predictive consistency
guard**. Temporarily hold each original curved family out of training, remove
its original predictive entries, retain newly proposed curves, and refit from
the regional center in both c arms. Compare predictions of the exact same
held original IDs and aliases using correlated calibration uncertainty. All
original points return to final accepted fits; this introduces no permanent
holdout. The frozen rule requires total old-minus-new score>2log2 and median
family gain>=0 in both arms, with valid phase convergence and visibility.

The rule was designed after seeing0390's geographic regression; the inspected
two-case result is not blinded validation. A random20 cohort was frozen before
fold scoring and includes rejected/no-proposal cases as exact incumbent
fallbacks. Original labels remain hypotheses, overlapping folds are dependent,
and the conditional Gaussian composite is not a calibrated Bayes factor.
Do not promote this guard from development examples alone. See the linked
report for its confirmation outcome. No ALGO version or production default
changes here. Next DBG01 cases are0221/0322, with0405 still in full evaluation
and skipped only in this bounded debug queue.

Random20 confirmation does not justify promotion: unrestricted growth raises
pooled association69.69→71.35% but worsens fitted-c mean1.742→2.195 km and
median1.468→1.631 km. The frozen guard accepts only0334, gives mean1.735 km,
and leaves median/P90 unchanged. Do not retune the guard against these GPS
outcomes. Preserve the current method; next0322 DBG01 should reuse its rejected
confirmation growth trial rather than rerunning it. All436 family folds and
872 paired endpoint/predictive density checks passed after preserving430
completed jobs and recovering six interrupted jobs with unchanged settings.

## Separate support rejection, numerical qualification and point evidence

[Iteration004](../2026_10_22_ds23_dbg01_iteration_004/README.md) closes0221/0322.
Curved reentry recovers28 points on0221, fitted-c error4.133→2.273 km. On0322,
a26-point curve passes frequency/alias/horizon checks but is rejected because
masked-out nominees enabled three physical orbit modes without two active
owners. Preserve incumbent modes and phase, remove unsupported new shape
terms, then rerun all original gates. It recovers26 points, error4.056→3.776 km.
The previously tested64-point union passes but worsens error to4.568 km.

A mechanical confirmation excludes0322 from the earlier random20. Offer only
old proposals rejected solely by owner support, not already-valid broad growth.
Three of19 scans recover231 associated points; fitted-c mean1.620→1.609 km,
median unchanged1.337 km, two improved/one worse/16 unchanged. This supports
the bookkeeping repair, not a new ALGO release or full-population accuracy gain.

Inventory points outside every graph track. Iteration004 tests all orphan
winning points in a normalized wrapped-CFO/clutter mixture with shared Gaussian
calibration uncertainty. A conditional signal probability is neither a verified
satellite identity nor an accepted track. No new hard associations are claimed
without separate validation. Initial prior sampling collapses; EM-guided
importance sampling is corrected by the full proposal density. Do not report
an apparent position minimum unless independent seeds, effective draws and
quadrature checks qualify at the proposed point, not just at the incumbent.

On0221 all nine proposed fine-grid points fail those checks; only the original
RF endpoints qualify. A large likelihood gain versus all-clutter is not a new
position solution. Existing linear evidence and new orphans share covariance:
their separately integrated product is a composite approximation. A joint
Gaussian conditioning control replays the original linear density and leaves
curved calibration outputs unchanged; it is not a reoptimized regional result.

When multi-start endpoints all fail gates, do not interpret their plotted
convergence as qualified localization. A bounded per-branch paired-feasibility
control on0322 finds a3.909 km alternative, but gain1.171<declared penalty2.773,
so it retains the incumbent. Keep that distinction in future DBG01 reports.
Following TLEs remain diagnostic only. Next scans are0272/0068; revisit a closed
case only for a new transferable hypothesis. The0.5 km full-DS23 goal remains.

## Iteration005: temporal predictive recovery and baseline qualification

See the [0272/0068 report](../2026_10_22_ds23_dbg01_iteration_005/README.md).
0272 gains106 curved position observations and148 total associations, reaching
73.34% with fitted-c error1.220 km. A separate screened temporal prototype
adds83 predictive points but error remains3.746 km; its independent control
worsens error. Do not add these separate experiments' counts or promote an
ALGO version from one favorable scan. Next bounded cases are0069/0291.

Temporal marginal emissions and a clutter state may nominate unused original
GLRT paths, but require correlated shared-calibration checks, whole-path
residual checks and the final paired gates. Keep all old and new predictive
evidence in one covariance block, with no calibration updates from recovered
paths. Treat post-selection identity scores and timestamp/CFO permutations
as compatibility/coherence diagnostics, not verified identity probabilities.
Reject complete paths instead of trimming individual residual outliers.

Audit the archived baseline against the **same** qualification criteria used
for new trials.0068's inherited phase for58133 exceeds15 s even though the
phase-reference refresh is clipped. Reference clipping does not constrain
the posterior phase. Its screened paths pass residual checks but still fail
the strict phase gate; an exact archived fallback is not a qualified new
solution. Retain the historical benchmark for comparison, with explicit
qualification flags; do not silently loosen the gate or remove the case.
All81 failed restart endpoints are diagnostic, not81 accepted convergences.

## Iteration006: residual feasibility is not association truth

See the [0069/0291 report](../2026_10_22_ds23_dbg01_iteration_006/README.md).
A bounded constrained fit of near-threshold supported-mode hypotheses admits
76 new position observations on0291, reaching74.95% association, but fitted-c
error worsens3.690→7.030 km. A19-case scan-disjoint confirmation also regresses
in mean and median despite105 additional associations beyond the support-only
control. Do not adopt this extension or weaken gates to increase counts.

Report unconstrained and constrained RF cost on the same mask, geographic
effects separately, and all cases in a confirmation cohort. A solver can move
position to make residual tests pass without establishing the identity or
improving location. Preserve complete observations and exact incumbent
fallbacks, including their own qualification status.

The full archived metadata audit reproduces all410 benchmark errors and finds
409 pass residual, phase, refresh and regional checks in both c arms; only0068
exceeds15s phase. This is a saved-record audit, not a fresh410-scan numerical
replay. Keep0068 in historical accuracy metrics with an explicit exception.
Clarify catalogue scope: the checked causal Space-Track archive contains only
Starlink records; “full catalogue” does not imply every orbital transmitter.
Next bounded cases are0227/0400. New ALGO releases still require full-DS23 gains.

## Iteration007: grouped linear prediction and full-population confirmation

See the [0227/0400 and410-scan report](../2026_10_22_ds23_dbg01_iteration_007/README.md).
Multiple unused linear fragments on different RX/channel owners can nominate
a new shared satellite family without calibrating receiver offsets or drift
from those lines. Keep old/new predictive observations in one normalized
joint density with the full curved-calibration covariance. At fixed position,
verify that predictive evidence never changes the original curved coefficients.

This experiment raises fitted-c GLRT association70.08→71.22% and lowers mean
error1.469→1.449 km, but median stays near1.179 km, fast-scan mean worsens
slightly, and three scans regress by more than500 m. Retain all410 cases and
report both c arms, per-mode summaries and post-fit-only ID losses. Do not
promote a new ALGO solely because the mean or association count improves.

For unused high-order graph tracks, inspect point leverage and cadence gaps.
0227's quartic has an isolated endpoint with leverage0.99991. A separately
discovered family predicts the19-point core. Compare whole-track satellite,
core plus uniform clutter, and unknown-curve models over the same original
observations, with a search penalty. Any derived predictive subset preserves
the original graph, CFO values and denominator; omitted IDs stay unassociated.
This development-only extension is not part of the frozen full-scan method.

Include the longest unused linear tracks in DBG01 when curved targets are
absent. Small single-line RMS is not identity proof. Following-TLE diagnostics
remain isolated from inference. Cross-check orbital means at native times
against an independent propagation API; covariance algebra alone cannot catch
an incorrectly broadcast frequency. Next bounded cases are0157/0207.

## Iteration008: same-receiver curvature and short-core duration checks

See the [0157/0207 report](../2026_10_22_ds23_dbg01_iteration_008/README.md).
Within one receiver, compare RF-normalized curves after removing separate
affine terms. A shared nonlinear curve must explain a common satellite plus
the modeled shared receiver smooth term. Compare shared versus independent
polynomials on identical native observations, with complexity penalties;
do not call this an identity probability or compare raw BIC across masks.

In0207 the original pair prefers different curvature, while a frozen HMM
recovers21 of22 points and leaves an isolated endpoint unused. The core is
measurably curved but spans13.93s, so the existing20s classification excludes
it. An explicit10s duration ablation requires250Hz nonlinear amplitude and
>10 BIC quadratic gain under every single-point deletion. Keep the published
classifier unchanged; any derived core preserves native CFOs, incumbent
likelihood rows, the original graph and all observation IDs.

Test recovering missing families before temporal orphan search. Preserve the
exact original coarse/fine receiver basis in appended paths, the graph
parent's protected modes and joint predictive covariance.0157 gains a useful
46-point curved family, reducing3.384→1.335km.0207 temporal coverage reaches
75.41% but worsens relative to its graph parent. Reject0157 paths that break
the parent's ACF gate; passing new paths cannot override a failed parent.
No new ALGO version is warranted. Move to0028/0311 after the bounded tests.

## Iteration009: partial masks, covariance units and intermediate descent states

See the [0028/0311 report](../2026_10_22_ds23_dbg01_iteration_009/README.md).
Keep whole-track nomination inputs distinct from general unused-point
inventories. Exclude partial or already active source components only from
the whole-track offer list; retain their original measurements and diagnose
unused contiguous blocks explicitly. Check scientific worker receipts before
dependent stages, even when the outer command returns zero.

For a partly used component, compare the prefix, unused suffix and whole
original source under the frozen mean, then restore the complete missing
mask without changing identities, aliases, priors or nuisance definitions.
0028's26-point suffix favors57434, but the restored77-point source fails
autocorrelation. Do not split at a mask boundary merely to weaken the
sample-count-dependent ACF threshold.

RF-only correlation shape may be learned from other same-RX polynomial
contrasts with target IDs excluded, provided inherited noise estimates and
their possible target reuse are disclosed. Validate on target RF contrasts
before position tests. Preserve other blocks and joint predictive covariance;
test the white-model null and independent predictive-density replay.
Whitened innovations are dimensionless: the existing noise screen's75Hz
floor must map to a unit normalized floor. Retain raw deterministic guards.
Here whitening removes correlation but raw slope/step fail and position does
not improve. All20 paired recovery trials reject; keep the incumbent.

Convergence plots must distinguish intermediate phase-round states from
final endpoints.0028's early boundary excursions are not final solutions.
Annotate starts, intermediate states and final coordinates; preserve per-round
coordinates and c-arm scheduling. Single-family ablations leave at least
3.070/2.897km on these scans, so they do not establish one sufficient bad
family. Move to0080/0257 after bounded tests. New ALGO releases still require
credible full-DS23 improvements, separate from this debug report series.

## Iteration010: short whole curves, protected-family conflicts and confirmation

See the [0080/0257 and20-scan report](../2026_10_22_ds23_dbg01_iteration_010/README.md).
The existing10s jackknife curvature rule can be applied to whole unused
sources without trimming endpoints or changing persisted graph contracts.
Require12points,250Hz linear-fit RMS and>10 quadratic BIC gain under every
single-point deletion. Preserve native CFOs, bases, IDs, old powers and parent
orbit support; simplify only unsupported new-family modes. Cold-fit the same
observations and candidates in both c arms, then independently replay gates.

0257 recovers31 calibration points and improves3.180→2.748km locally.
The declared maximum-point policy must retain the union even though a
GPS-ranked14-point single would look better.20 scan-disjoint same-site cases
recover394 calibration points but worsen fitted-c mean and both c0 accuracy
metrics. Do not promote the rule from its local success or coverage gain.

In0080, lower-error unconstrained temporal fits violate67014's source slope
gate. The unchanged near-feasible solver admits78 predictive points and
reaches80.83% association, but returns to3.291km. A passing path cannot
override a failing parent. The only paired-passing family deletion,67014,
gives0.737km but is GPS-ranked diagnostic evidence, not an RF-only rejection
rule. Same-RX normalized curvature favors keeping nearby66381 evidence
separate; do not force that merge. Surface minima and gates must be reported
together. None of81 unconstrained0080 restarts passes paired gates.

Support rescued scans without legacy fit-choice archives explicitly: retain
the current complete assignment and actual cold discoveries, record the
missing archival pool, and discard all warm nuisance state. Keep empty
predictive cases in evaluation; a calibration-only problem has no predictive
density API to audit. Preserve failed results, reuse successful cases exactly,
and repair missing report metadata from frozen numerical state without
changing positions. Continue to0163/0209; reuse0209's existing short-curve
confirmation evidence. Inspect prior RF-only family-adequacy work before
adding a deletion or nuisance rule. Full-DS23 ALGO promotion remains separate.

### Iteration011: paired RF evidence, exact native timestamps and parent ambiguity

[Iteration011](../2026_10_22_ds23_dbg01_iteration_011/README.md) closes0163/0209.
Keep full-population decision replay distinct from new end-to-end inference:
the paired positive-RF-gain guard reuses410 saved causal cases and changes only
0080/0273, improving fitted-c mean/median to1.462402/1.167197km with unchanged
point IDs/coverage. Time-block intervals reach zero and the evidence remains
same-site; retain the published reference and do not issue a new ALGO version.

For two already qualified graph parents, a normalized RF-bound comparison is
allowed only when their entire calibration masks and predictive factors match.
Require >2log2 improvement in both c arms for this bounded alternative. It can
worsen geography before additional evidence is included:0163's better RF parent
alone reaches3.401km. Its67 screened persistent predictive points yield2.709km;
the default parent's temporal fit fails a source slope gate. Report both parent
and child, and do not compare raw scores across different masks. On0209 the
existing temporal rule gives72.19% and2.907km; reuse prior short-curve evidence.

Actual overlapping intervals matter for RF-only curvature checks.0163's two
same-RX nominees favor a common polynomial over whole unequal windows but
strongly favor separate curvature over their overlap. This is a diagnostic,
not permission to force a shared identity. Both scans'81-start searches return
the incumbent and no individual family deletion cures the bias.

When appending native observations, union their exact timestamps into the scan
time grid and recompute every track's lookup. Never use unchecked searchsorted
against the old graph-only grid. The repaired adapter preserves14 prior saved
objectives, coefficients and membership sets exactly; only failed0209 was
resumed. Preserve the original failures and pre-fix sources. Both c arms and
all final source gates remain mandatory. Continue to0215/0281 without dwelling
on closed cases absent a transferable new hypothesis.
