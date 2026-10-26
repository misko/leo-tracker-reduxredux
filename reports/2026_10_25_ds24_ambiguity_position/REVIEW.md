# Fast-scan localization: what the experiments justify next

Reviewed 2026-10-26 UTC, including the completed unused-source inventory in this
report. The retained reference is fresh ALGO02-v1 with qualified causal signed
orbital-timing means and equal-assignment-prior family comparison. There is no
new ALGO promotion. These are findings from the repository's experiments, not a
new literature survey.

The main opportunity is to distinguish useful physical constraints from smooth
but ambiguous curves. More optimizer starts, more polynomial members and lower
frequency RMS have all been tested without reliably producing better positions.
The evidence implicates shared orbital timing/shape uncertainty and uncertain
source identities. It does not establish one universal fault or a hard accuracy
floor. Recent work has eliminated explanations more often than it has improved
the retained estimator; that distinction should guide the next allocation of
effort.

| Matched comparison | Mean error c=0, km | Mean error fitted-c, km | Decision supported |
| --- | ---: | ---: | --- |
| ALGO01 → ALGO02, 404 common DS23 outputs | 1.870 → 1.520 | 1.870 → 1.508 | Substantial retained gain; outputs fell from 407/413 to 404/413. |
| Signed-prior reference → equal-prior family comparison, 410 DS23 scans | 1.509 → 1.479 | 1.498 → 1.469 | Small retained gain; temporal-block uncertainty limits extrapolation. |
| DS24 CH1–8 / CH1–4 / CH5–8, identical 24 usable scans | 1.202 / 1.538 / 2.040 | 1.220 / 1.558 / 2.040 | All channels already help on average. The cohort is 24 usable out of 34 recordings. |
| Smooth RX1 correction, 24 development scans | 1.202 → 1.112 | 1.220 → 1.120 | Development lead requiring confirmation. |
| Same frozen RX1 policy, eight later scans | 1.243 → 1.240 | 1.239 → 1.224 | Development-sized gain did not transfer; both P95 tails worsened. |

These are separate comparisons, not additive steps in one benchmark. Sources:
[ALGO02](../2026_10_19_algo02_ds23_full/README.md),
[family comparison](../2026_10_22_ds23_family_cavity_full_assessment/README.md),
[channel halves](../2026_10_24_ds24_channel_halves/README.md),
[later RX1 test and synthetic controls](../2026_10_25_ds24_phase_shape_validation/README.md).

![Measured gains and failed transfer](../2026_10_25_ds24_source_coherence/review_figures/measured_results.png)

The original graph, EM, Hough and multiple-hypothesis constructors could put
roughly 90–93% of DSX01 S01 points into polynomials. That establishes curve
membership, not satellite identity. The reviewed DS24 reference uses
78,067/108,600 points, 71.8849%, in its position likelihood; postfit association
is a third, different count. The full DS23 ALGO04 recovery candidate raises
fitted-c association from 70.08% to 75.08% while worsening mean error from
1.469 to 1.591 km and P95 from 3.157 to 3.473 km. Its c=0 mean also worsens,
1.479 to 1.607 km. We should keep reporting coverage, but should not accept a
method because it approaches 90%.
[Recovery comparison](../2026_10_23_algo04_candidate_full_ds23/README.md).

**The strongest supported bottleneck is separating position from orbital
timing and shape.** In the local DS24 information diagnostic, median weak-axis
uncertainty is 534 m under the model, 386 m with receiver terms treated as known,
110 m with timing known, and 56 m with timing and shape known. The median
strongest timing/weak-position correlation is 0.935. Bands share a median
11 calibration families, and their weak position directions differ by only
17.7 degrees. More channels often observe the same uncertain satellite motion.
They add useful data without supplying an independent orbit reference.

![Conditional model information, not achieved geographic error](../2026_10_25_ds24_source_coherence/review_figures/conditional_information.png)

The synthetic factorial adds a useful qualification: even with correct fixed
labels, eight fitted-c realizations have mean error 0.469 km and maximum
1.094 km. Removing generating timing deviations gives mean 0.403 km; removing
shape gives 0.405 km; removing both gives 0.297 km. Inference does not receive
the true nuisance values. One zero-shape realization fails the original gates,
and all outcomes remain reported. Both effects matter in that constructed
experiment. It is neither an identity test nor evidence that real-data priors
should be made narrower. Synthetic and real means cannot be subtracted to
estimate a physical bias.
[Factorial experiment](../2026_10_25_ds24_phase_shape_validation/README.md).

**Several attractive fixes have already had a fair test.** Thirty targeted
restarts agree within 2.06 cm, and four channel-half assignment transfers find
no qualified better full-data result. That lowers the value of generic
multistart for the tested models; discrete identities remain an open question.
Remeasuring 322 RX2 curves reduces median fixed-degree scatter from 78.07 to
22.18 Hz without a qualified cohort gain. The RX1 correction's weak later
transfer likewise argues against another unconstrained smooth correction.
[Bottleneck study](../2026_10_24_ds24_bottlenecks/README.md).

Adding previously missing parent orbit covariance completes 16 fits but yields
zero qualified candidate pairs out of four. Rejected raw means worsen by
8.4/9.9 m. A phase-dependent shape-design probe has a maximum 0.571 m local
movement proxy in its tested contexts. Earlier DS23 local nonlinear-phase
integration has a maximum 22.795 m proxy; Gaussian log-volume removal moves
positions a median 5.84 m and maximum 15.89 m. These results lower the priority
of repeating the same covariance, integration or normalization changes. They
do not prove every possible nonlinear or physical discrepancy is negligible.
[Parent uncertainty](../2026_10_25_ds24_parent_orbit_uncertainty/README.md),
[coupling and source-coherence review](../2026_10_25_ds24_source_coherence/REVIEW.md),
[methods inventory](../2026_10_25_ds24_next_directions_review/methods/FINDINGS.md).

Active-family soft identities, grouped new-family prediction, orphan mixtures,
temporal path recovery, causal TLE-history prediction, correlated orbit priors
and sample-clock corrections also have existing tests. A new proposal must
name the missing mechanism rather than rename one of these approaches. For
example, the old active-family soft-label test lacks absent families and an
unresolved-source outcome; a whole-source hypothesis model addressing those
specific omissions is a different test. The current bounded pilot is described
in [ambiguity findings](ambiguity/FINDINGS.md).

**The completed ambiguity pilot supplies a material new lead.** In DS24-0011,
the archived hard label 58175 remains the best point-evidence candidate at all
three positions in both c arms. Its normalized weight within the declared
mixture is nevertheless only about 0.50–0.60, and varies with position.
Preserving the alternative whole-source assignments changes the finite-difference
RF slope relative to fixing 58175. Scaling that change by the archived weak-axis
curvature gives -305 m for c=0 and -254 m for fitted-c, with propagated
score-bound intervals approximately [-386,-224] m and [-332,-176] m. The sign
refers to the archived axis, not a direction toward evaluation GPS.

All three predeclared physical-class weights give the same material conclusion.
This is a potential added source: it is currently unaccepted, and the comparison
is mixture versus hard addition, not mixture versus the deployed no-addition
reference. The scaled secant is not a true derivative, an optimized displacement
or a predicted error improvement. It also depends on an uncalibrated physical/
unresolved model and finite candidate pool. The result justifies a bounded
position-policy experiment; it does not establish which satellite is correct.

DS24-0012 reaches its case time cap during the last center reference check,
before side probes; it provides no position-slope conclusion. Across the pilot,
71 of 108 declared slots complete and 37 remain failed or missing. The 63
complete physical point-quadrature checks are stable, but none certifies the
absolute evidence to the declared 0.001 tolerance. Conservative full-evidence
bounds are still sufficient for the reported 0011 secant decision. Do not
confuse point-integral stability with absolute precision or hide the unfinished
second case. Total work including preparation is 445.290 worker-seconds.

**The latest inventory gives concrete follow-up cases, with limited expected
size.** Across all 24 usable DS24 scans, 3,265 original owners yield 148 complete
unused curved owners. Two lack required active-family uncertainty columns;
146 have complete design calculations. Among the 115 outside the declared
prior source-challenge coverage, 24 meet a frozen 5% weak-variance threshold in
both c arms, spread over 12 scans. All scans are development data; this is not
fresh validation or an exhaustive proof that an owner was never inspected.

The first four chronological selections are fixed at 0014–0017:

| Scan | Complete track | Assumed satellite | Points | Modeled weak-SD reduction, c0 / fitted | Original canonical nomination |
| --- | --- | ---: | ---: | ---: | --- |
| 0014 | RX1 CH1 T004 | 59733 | 87 | 31.9 / 32.0 m | Incompatible; no feasible candidate |
| 0015 | RX2 CH4 T004 | 68904 | 29 | 29.6 / 29.8 m | Incompatible; no feasible candidate |
| 0016 | RX2 CH2 T004 | 59786 | 40 | 20.1 / 20.0 m | Compatible; one feasible candidate |
| 0017 | RX1 CH5 T004 | 100180 / A0180 | 51 | 46.9 / 47.0 m | Incompatible; no feasible candidate |

These are reductions of conditional model uncertainty if the assumed
identities are valid, not measured accuracy gains. All four tracks pass their
archived polynomial structure check; three fail the archived satellite
compatibility screen. This is a particularly clear example of the remaining
problem: smooth and potentially informative does not mean correctly identified.
Keep these failures in the selected panel; replacing them with easier cases
would defeat the diagnosis.

![Length versus useful conditional information](inventory/report/length_vs_information.png)

Information ranking differs from count ranking in two cases and duration
ranking in three. In 0015, a 77-point owner offers only about 0.24–0.27% modeled
variance reduction, whereas the selected 29-point owner offers about 9.4–9.5%.
The larger conditional gain does not override its compatibility failure.
[Complete inventory, all exclusions and controls](inventory/FINDINGS.md).

My recommended next work is two small scientific branches and one independent
reviewer, with a firm decision at each branch's end. The new 0011 result raises
the ambiguity policy above IQ injection in the immediate order:

1. **Test a conservative whole-source ambiguity policy on position.** Compare
   no addition, the fixed hard-label addition and the whole-source mixture on
   the same qualified target, causal candidate pool, aliases, physical law and
   parent uncertainty. Keep an unresolved outcome and original source-adequacy
   requirements; averaging inadequate physical fits is not a repair. A small
   common RF-selected position profile should first establish that the
   numerically tractable objective agrees with the bounded pilot. Then use a
   frozen paired fit and exact reference fallback. Evaluate geography only
   after RF choices are fixed. The decision is whether uncertainty-aware
   addition helps the actual estimator relative to doing nothing, not whether
   it beats one hard label on target likelihood. Keep 0012's unresolved outcome
   without silently replacing it or extending the failed integration.

2. **Qualify the four information-selected complete owners.** Reuse the
   ordinary causal catalogue nomination and compare the same full observations
   against plausible satellites and a proper unresolved model. Retain aliases,
   visibility and shared receiver/orbit uncertainty. Explain the three original
   incompatibilities explicitly: residual shape, phase support, identity,
   ownership or another recorded gate. Where a separately selected complete
   owner exists, require prediction of it without treating same-family orbit
   errors as independent. A candidate that cannot explain its whole source
   stays unresolved. Winning a finite candidate comparison is insufficient:
   freeze adequacy/abstention and original support/ownership requirements before
   any position test. If the qualified identity changes, recompute its information;
   the old label's predicted gain does not transfer to a different satellite.
   At most one qualified addition per scan then enters a
   paired position comparison with exact reference fallback. This tests whether
   useful geometry is actually recoverable, rather than whether we can improve
   coverage by changing gates.

3. **Prepare the distinct measurement-selection test on existing IQ.** The
   curve-level controls fix or inherit detection and tracking decisions; they
   cannot expose winner-dependent GLRT errors or crossing-induced ownership.
   One DS24-0011 original 10 MS/s chunk is available with matching manifest/index
   hashes. First bind a frozen detector and reproduce an unchanged archived
   window. Only if that parity and the signal/noise inputs qualify, run a small
   predeclared clean/weak/crossing injection test through actual peak selection
   and track construction. Failure to establish parity is a stop outcome, not
   justification for a larger IQ campaign. No new RF collection is needed or
   proposed. [Availability and current limitations](REPLAY_AVAILABILITY.md).

The IQ branch should initially stop at detector parity while the two scientific
branches above resolve their decisions. Do not turn every promising diagnostic
into another full pipeline campaign. Avoid returning indefinitely to the already
studied 0013 CH4 split while the broader selected panel remains untested.

Sample rate and receiver direction remain unresolved causal questions, but are
lower-priority explanations from the present evidence. All compared fast scans
are 10 MS/s. The nominal 40-degree feed separation changes sky coverage; it is
not a calibrated bearing or separated-station baseline. The raw metadata now
show aggregate digital power, which can help gain/clipping diagnostics, but do
not establish source-specific RSSI or antenna-bearing measurements. A future
sample-rate or direction claim needs a matched measurement experiment, not a
correlation between different recording modes.

Before another full-dataset campaign, require one implementable frozen policy,
matched c=0/fitted-c inputs and budgets, original-gate/failure accounting and
separate frequency-fit, likelihood-membership, postfit-coverage and geographic
metrics. Test mean and tails on an exposure-checked later block, then broaden
only if the gain survives. All current DS24 and eight RX1V outcomes are now
development evidence. None demonstrates transfer to a new location. Regional
inference remains in the 25×25 km box centered at 37.906, -122.545; the known
evaluation coordinate is not a candidate selector, prior or acceptance rule.
