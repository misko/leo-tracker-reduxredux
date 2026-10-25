**Decision review after the completed parent-orbit experiment**

The best next small experiment is an identity-support falsification with a
defined observation law and usable numerical comparisons. For a substantial
precision improvement, the larger opportunity is an independently justified
timing/orbit or geometric constraint. Another receiver basis, more points on the
same uncertain family, or a blanket covariance change has weak support from the
completed comparisons. This review performs no new simulation, fit, IQ read or
geographic selection.

The research reference remains fresh ALGO02-v1 plus qualified causal signed
orbital-timing priors and equal-assignment-prior family cavity. Every comparison
below keeps c=0 and fitted c distinct. The datasets, baselines and gains cannot
be added across studies.

| Evidence | What it establishes | What it does not establish |
| --- | --- | --- |
| ALGO01→ALGO02, 404 common qualified DS23 scans: fitted-c mean/median 1.870/1.602→1.508/1.249 km; qualified outputs 407/413→404/413. | A substantial broad within-site improvement, with an availability tradeoff. | Transfer to another location or a sub-500-m fast-scan method. |
| Full-DS23 family replacement: fitted-c mean 1.498→1.469 km; 40 improve, 34 worsen, 336 retain reference. | A modest improvement worth preserving, with block-dependence uncertainty. | Reliable truth labels or a large general identity gain. |
| ALGO04 recovery, same 410 scans: fitted-c coverage 70.08→75.08%, mean 1.469→1.591 km, P95 3.157→3.473 km; c0 also worsens. | Higher association coverage can worsen localization. | That all unassociated points are useless; membership and identity still differ. |
| All 24 DS24 channel controls: c0/fitted-c means 1.202/1.220 km full band versus 1.538/1.558 low half and 2.040/2.040 high half. | The extra channels already add useful information. | Independent orbital constraints for each extra channel. |
| RX1 correction: development mean gain about 90/100 m; frozen later-eight gain only 2.7/15.4 m, with both tails worse. | Development receiver gains did not reproduce at comparable size. | A universal receiver defect, or zero receiver contribution. |
| Parent physical uncertainty: all 16 fits complete; 0/4 candidate pairs qualify; raw means worsen 8.4/9.9 m; policies remain exact reference. | Missing covariance materially changes weighting, but this adapter gives no qualified gain. | That true physical shape variance is zero, or that its nuisance means are calibrated orbit corrections. |

Sources: [ALGO02](https://github.com/misko/leo-tracker-reduxredux/blob/e80f6d6776bd429936119fe15332960c36824269/reports/2026_10_19_algo02_ds23_full/README.md),
[family replacement](https://github.com/misko/leo-tracker-reduxredux/blob/e80f6d6776bd429936119fe15332960c36824269/reports/2026_10_22_ds23_family_cavity_full_assessment/README.md),
[rejected recovery](https://github.com/misko/leo-tracker-reduxredux/blob/e80f6d6776bd429936119fe15332960c36824269/reports/2026_10_23_algo04_candidate_full_ds23/README.md),
[channel and nuisance review](https://github.com/misko/leo-tracker-reduxredux/blob/e80f6d6776bd429936119fe15332960c36824269/reports/2026_10_25_ds24_phase_shape_validation/README.md),
and [completed parent uncertainty](https://github.com/misko/leo-tracker-reduxredux/blob/e80f6d6776bd429936119fe15332960c36824269/reports/2026_10_25_ds24_parent_orbit_uncertainty/README.md).

The last result is especially informative about qualification. Conservative
curved failures are actual primitive conditional-residual failures with original
support frozen, not new owner-only vetoes. Literal full-mean residuals pass but
expanded ownership fails. New posterior means can explain the structure without
independently establishing a physical correction. Neither changing the gate view
after evaluation nor narrowing priors is justified.

**1. Make the identity experiment falsifiable before another position addition.**

The preceding nomination control already shortlisted and raw-ranked all eight
physical generating labels correctly. Seven physical orderings qualified per
arm; none of four polynomial-null orderings qualified numerically. This was an
easy-physical/extreme-null pilot, not evidence of calibrated acceptance or a
shortlist failure. Its generator/screen use the full parent, whereas exact
scores remove observed shortlisted families. That response-dependent change in
the conditioning mean/covariance prevents a matching conditional-law claim.
[Exact prior result and failures](https://github.com/misko/leo-tracker-reduxredux/blob/e80f6d6776bd429936119fe15332960c36824269/reports/2026_10_25_ds24_nomination_information/nomination/FINDINGS.md).

First repair only the two demonstrated behaviors and replay the unchanged 12
old draws as regression fixtures: impossible phases contribute zero likelihood
under the original phase normalization; very poor alternatives need stable
log-integrals or verified ordering bounds. Do not silently change to a visible-
phase-conditioned prior, a post hoc relative tolerance or a winner-only exemption.
An integral with invisible phases set to zero is a joint observed/detected
likelihood; a proper generative interpretation retains the corresponding
no-detection probability. The fresh control must account for that distinction.

For a subsequent fresh panel, a lean proposal is two inherited layouts, one
response-free confusable pair per layout, one draw from each identity and one
declared polynomial null per layout: six observations. Freeze pair selection,
seeds, all priors and a common Gaussian background (mu,C) before any CFO draw.
Generation, ordinary full-catalogue nomination and primary exact scoring use
that same background; truth must never force a shortlist entry. Retain the old
full-parent→shortlist-cavity route separately on identical observations. c0 is
the generating-law control; fitted c is same-data sensitivity, not another
independent realization. This is at most 192 fresh candidate contexts across
two routes/two arms, under a shared 600 s numerical cap including regression
work, two workers and one BLAS thread each.
Any ordinary-versus-known-label comparison must use identical observations and
the same conditional background/law, differing only in label availability.

There is a necessary scope limit: a fixed exogenous background plus a fresh
target phase/shape prior for every catalogue identity is a well-defined target
experiment. For labels already active in the real parent, it is not the fully
shared-family conditional p(target|parent,identity). A literal common cavity
permitting fresh priors for every full-catalogue label would remove all parent
families and lose its calibrated context. Preserve this distinction rather than
hide active-family evidence or call the control end-to-end calibration.
Generating identities can be restricted by pre-draw geometry to fully visible
support; retain partial-visibility competitors. Otherwise archive no-detection
draws without rerolling. Report recall, unresolved comparisons and exact
physical/null ranks, never a real identity threshold from six examples.

Stop if the numerical rule cannot decide the old obvious failures within its
cap, or if the common-law construction remains ambiguous. No position fits or
new accepted associations follow automatically from a successful synthetic rank.

**2. Seek an independent observable, with an information test before processing.**

The local fitted-c weak-axis scale is 534 m, versus 386 m with receiver terms
known, 110 m with orbital timing known, and 56 m with timing and shape known.
These conditional oracles are not achieved errors or calibrated confidence.
The strongest timing/weak-position correlation is 0.935, and bands share many
families. A second source from the same satellite inherits its orbital error.
[Information and measurement audit](https://github.com/misko/leo-tracker-reduxredux/blob/e80f6d6776bd429936119fe15332960c36824269/reports/2026_10_24_ds24_bottlenecks/README.md).

Do a bounded feasibility check on existing material before another estimator:
is there a separately observable frame/symbol timing, known-pilot relation,
documented clock reference, calibrated directional measurement or independent
orbit product that constrains a direction confounded in CFO? Verify its actual
public contract and time/clock provenance. Project its sensitivity through the
current receiver/phase/shape nuisance space. Stop if it is only a transformation
of the same CFO observations, lacks an identifiable reference, or supplies
negligible additional direction. A measured cross-RX difference is not a new
independent likelihood term when its source CFOs are already included.

If an existing-IQ observable passes that check, use a few predeclared native
windows and sources, compare its new observable against the original exporter,
and hold complete independent families out. Its first outcome is reference,
uncertainty and support, not a geographic fit. Stable frame periodicity alone
does not provide absolute transmit time; the present 40-degree feed separation
is not a measured bearing or separated base station. No new RF collection is
authorized by this recommendation.

This must differ from prior work. RX2 remeasurement already reduced median
fixed-degree scatter 78.07→22.18 Hz without qualified cohort accuracy gain.
The sample-clock time/frequency coupling was also tested on DS23-0257/0202:
at 100-ppm engineering prior SD, fitted-c errors changed 3.699→3.688 km and
3.060→2.974 km. Those fitted clock offsets were not independent clock evidence.
[Clock control](https://github.com/misko/leo-tracker-reduxredux/blob/e80f6d6776bd429936119fe15332960c36824269/reports/2026_10_19_ds23_robust_predictive_linear/README.md).
Causal orbit-correlation forecasts already failed whole-satellite and publication-
block qualification; median timing/mean-motion correlation was only 0.054 and
baseline timing-proxy central-95% coverage 87–89%. Later historical TLEs were
forecast proxies, not authenticated orbit truth. Repeating the same correlation
or narrowing phase priors does not supply the missing independent information.
[Forecast result](https://github.com/misko/leo-tracker-reduxredux/blob/e80f6d6776bd429936119fe15332960c36824269/reports/2026_10_24_ds24_receiver_orbit_controls/README.md).

**3. If no independent measurement exists, test one omitted coupling, not a rewrite.**

A full Bayesian rewrite is premature. Previous parent nonlinear-phase work
already evaluated 829,440 curved/joint draws on five DS23 cases and found at
most 22.795 m predicted local movement with fixed Gamma and shape design.
R2 later integrated only a new target's phase. Neither establishes full parent
hierarchical integration, but an unchanged local phase slice would repeat work.
[Audited methods and exact phase sources](https://github.com/misko/leo-tracker-reduxredux/blob/e80f6d6776bd429936119fe15332960c36824269/reports/2026_10_25_ds24_next_directions_review/methods/FINDINGS.md).

One distinct small question is whether allowing ACTIVE-PARENT calibration's
physical-mode design B(phi) to change with phase changes the normalized RF
objective/gradient materially. Predictive-target and identity kernels already
evaluate B(phi) at every phase node; those are not the missing parent control.
Use at most two fixed fast contexts and RF-selected probe positions, matching
the phase law, normalization, covariance and precisions on both sides; compare
two numerical rules. The existing synthetic factorial changes generating
timing and shape under unchanged inference; it does not isolate this integration
approximation. Stop at an unresolved integral or negligible stable gradient
effect. A positive diagnostic would justify a separately frozen bounded fit;
it would not itself demonstrate accuracy or validate priors.

**Validation after development exposure.**

The 24 old DS24 cases, eight later RX1V cases and current four-case explanations
are exposed development evidence. Randomly splitting them again, preserving
unknown errors in one table, or selecting another candidate on them does not
create validation. Keep using them as regression/ablation fixtures.

An existing unused recording block is usable only after exact recording/session,
capture and content-hash membership has been audited against all prior manifests
and geographic reports. Production inference completion is not proof that an
error was inspected; absence from one published 24-row table is not proof of
nonexposure. If provenance cannot establish a clean block, label exposure unknown
and do not claim blind validation. No unexamined corpus block is established by
this review.

Once such a block exists, freeze chronological inclusion, all failures/no
replacement, baseline, candidate, parameters, both c arms, gates and budgets
before errors are released. Seal RF decisions first. Grade all selected cases,
separating raw diagnostics, exact paired fallbacks, qualified-output rate,
complete accepted-ID retention, likelihood/postfit coverage, mean/median/P95 and
group-dependent uncertainty. Require improved distributions and credible
calibration, not just in-sample score or association count, before promotion.
Same-site improvement still would not establish new-location transfer. If no
clean existing block is available, the next genuinely prospective session needs
a separate authorized recording plan; it cannot be manufactured by repartition.

Do not repeat generic multistart, unchanged soft identities, broad full-corpus
recovery, arbitrary receiver flexibility, identical sample-clock columns,
phase-width sweeps, Gaussian-volume removal or GPS-selected family vetoes.
Keep current operations unchanged while the next small experiment resolves one
of the explicit missing pieces above.
