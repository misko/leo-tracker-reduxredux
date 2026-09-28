# Association-specific receiver-order experiment

## Decision and question

The next direction experiment should test whether a frozen satellite trajectory's **signed passage
through the nominal RX0/RX1 beam plane** predicts the time evolution of receiver-asymmetric
detection evidence. It should not reduce the observations to the first candidate inside a frequency
gate. The concrete question is:

> After a frequency-only, causal association posterior and an explicit absent state are frozen, does
> the candidate-specific predicted RX0-before-RX1 order improve the held predictive density of
> frequency-free receiver marks over an unsigned-geometry model, and does that gain disappear when
> receiver labels or signed trajectory order are reversed?

This is feasible on the existing corpus as a bounded development experiment. DS8 is now explored,
so it can confirm arithmetic and show transfer behavior but cannot serve as a new blind panel. A
positive result would support a model-specific signed receiver/trajectory relation. It would not
prove satellite identity, physical beam-entry time, antenna pattern, cable mapping, or location.

## Why the earlier experiments do not answer it

The receiver-order export produced one uncensored reception lag and no held lag. Its 2.5 kHz
periodic gate defined the hits, most detections were intermittent, and ambiguity/censoring removed
nearly all sequence endpoints. The detailed follow-up found only runs of three successive sampled
hits and emphasized that observed nonmatches are not physical transition boundaries. Repeating a
first-hit or threshold-crossing analysis would reproduce those limitations.

The geometry experiments retained complete candidate sets and proper clutter/presence states, but
their tilt term tested generic predictive reception. In the final DS8 panel, T beat D on all four
records while T beat the causal reference on only one; the receiver-swap contrast was positive on
only two of four for the causal-trained family. That result does not directly compare observed
RX0-before-RX1 evolution with a candidate's predicted signed crossing. The causal frequency
reference also gained 8.776 nats/window over the uniform reference, far larger than the geometry
contrasts. This proposed experiment therefore uses a primary outcome that contains no frequency
residual, to separate the attribution. A correctly specified joint likelihood remains another
possible approach; these results do not rule it out.

## Frozen population and three-way separation

Use the existing six calibration recordings for all coefficient fitting and design development.
Apply leave-one-record-out checks inside those six. After the design is frozen, report transfer on
the four prior evaluation records and DS8 as already-explored panels, separately. Never pool them
into calibration or use their signs to choose a threshold, horizon, covariate, or model family.

Keep the existing exact `(session, channel, edge, actual RF)` lanes, grouped roles, training-only
candidate bank, alias mapping, receiver-bias calibration, top-three weights and omitted-catalogue
mass. Each paired source window contributes once. Qualified empty sets remain observations; missing
or malformed receivers remain exclusions. Do not select rows by future frequency residual,
candidate rank, unique match, visibility success, observed order, or whether a crossing occurs in
the scored block.

Separate three latent questions in the model:

1. **Presence:** an absent state emits the empirical clutter/count/mark distribution. A dynamic
   present state may refresh between absent and nominated candidates. It cannot be represented by
   renormalizing the candidate shortlist.
2. **Identity hypothesis:** the present states are every retained track-candidate pair plus the
   frozen omitted-catalogue branch. Candidate weights start from training-only nomination priors.
   Reception frequencies may update them through the frozen causal periodic density, score before
   update, but receiver-order marks may not affect this conditioning step.
3. **Signed direction:** conditional on candidate state, only the frequency-free receiver mark
   likelihood sees the candidate's signed beam-crossing covariate. It can update identity weights
   after its own score is recorded, but it cannot alter CFO, alias, Doppler mean, visibility, or the
   observation population.

This separation makes a direction gain distinguishable from a generic target-presence gain. Since
no decoded truth label exists, identity evidence remains relative predictive support among frozen
hypotheses rather than an accuracy claim.

## Predicted signed crossing

For each frozen candidate, propagate the same causal TLE and pose authority already used for its
frequency forecast. At every eligible window export the LOS unit vector and its analytic or
centrally differenced angular velocity. Under the provisional RX0-west/RX1-east convention, define
the frozen nominal boresights

```text
n0 = (-sin(10 deg), 0, cos(10 deg))
n1 = (+sin(10 deg), 0, cos(10 deg)).
```

Let `q_h(t) = dot(n1 - n0, LOS_h(t))`. A zero of `q_h` is the nominal equal-boresight plane. The
sign of `dq_h/dt` specifies the candidate's predicted receiver order; the fitted receiver-response
slope specifies which sign corresponds to RX0-first under the provisional label mapping. Do not
infer order from Doppler slope alone. Export the crossing time only when a bracketed zero exists;
otherwise retain the full signed `q_h(t)` sequence rather than extrapolating a crossing.

Also export `tau_hr`, the scheduled or interpolated time maximizing `dot(n_r, LOS_h(t))` for each
receiver when an interior bracket exists. The conventional predicted order is the sign of
`tau_h1 - tau_h0`; it must agree with the local equal-plane slope before a candidate is called
order-informative. Boundary optima are censored, not extrapolated arrival times. These quantities
describe nominal forecast geometry rather than measured antenna maxima.

The pose authority says physical RX1 points west and RX2 east, with a provisional mapping to
software RX0/RX1; world tilt and RF phase centers are unmeasured. Treat the documented mapping and
its swapped alternative as two fixed conventions. A result that prefers one is evidence about the
predictive label convention, not validation of a geographic travel direction or cable trace.

Before outcome scoring, calculate a **support diagnostic** from forecasts and priors only. A lane is
direction-informative only when at least two materially weighted candidates disagree in crossing
order or have separated crossing times within the observed schedule. Report prior-weighted entropy,
order mass, crossing-time separation, and the number of scheduled samples on each side. Keep
uninformative lanes in the presence score but assign them zero association-direction information;
do not call a common order shared by every candidate identity evidence.

## Frequency-free receiver observation

For receiver `r` in paired window `i`, use only the observed candidate count and detector marks
whose definitions do not contain CFO: rank, margin or the underlying frozen detector statistic if
publicly available. Exclude candidate frequency, wrapped residual, closest-candidate identity and
forecast compatibility. Fit the mark calibration on the six calibration reception subsets only,
with receiver and lane intercepts to absorb stable sensitivity differences. Preserve the unordered
candidate set and integrate which, if any, candidate is signal-origin; never select one detection.

The paired receiver likelihood should share a window-level reception random effect. Compare these
nested arms with identical absent-state, count, mark, lane, receiver, rate and time nuisance terms:

| Arm | Candidate-dependent receiver term | Purpose |
|---|---|---|
| P | none | presence and receiver sensitivity only |
| U | an even function of `q_h(t)` and elevation | candidate geometry without signed order |
| O | U plus `receiver_sign * q_h(t)` and a predeclared smooth time interaction | predicted RX0/RX1 order |

Use one shared, strongly regularized odd slope in O. If a response bandwidth is necessary, freeze
its grid from calibration-only cross-validation; do not estimate a separate crossing width per
candidate. O with its odd slope fixed to zero must reproduce U exactly, and U with all geometry
terms fixed to zero must reproduce P.

The primary endpoint is held frequency-free mark/count log predictive density `O - U`, normalized
within recording and averaged equally across recordings. `U - P` measures unsigned candidate
geometry; it cannot be reported as direction evidence. Report informative and uninformative lane
strata, but the population and stratum rule must be frozen from forecasts alone.

## Association-specific validation

A positive O-U score can still reflect a generic receiver/time pattern if all candidates predict
the same order. Require all of the following before describing association-specific direction
support:

1. O beats U on the primary held score and is positive across a prespecified majority of recording
   clusters; with so few clusters, signs are descriptive rather than a discovery p-value.
2. O beats **receiver swap**, which exchanges `n0` and `n1` while preserving receiver labels,
   offsets, marks and times.
3. O beats **signed trajectory reversal**, `q_h(t) -> q_h(t_end + t_start - t)`, while retaining
   actual observations, Doppler forecasts and causal history order.
4. O beats a **candidate permutation control** that permutes signed `q_h` trajectories among
   nominated candidates within the same lane while preserving each candidate's frequency posterior,
   visibility rate and prior mass. Freeze one digest-derived permutation per lane; do not search
   permutations after outcomes.
5. The gain is concentrated in forecast-informative lanes where nominated candidates disagree,
   rather than only in lanes with one effective candidate or common predicted order.

The candidate permutation is the crucial identity-versus-presence control. Swap and reversal test
receiver/time semantics, while permutation tests whether the signed pattern belongs to the same
candidate favored by independent frequency evidence.

As a prespecified secondary bridge, split the held block by grouped source windows into an early
direction-update segment and a later frequency-score segment. Score early frequency-free marks
before using them to update candidate weights, then score the complete later candidate frequencies
under the already frozen causal periodic density. Compare that later frequency score with weights
that did and did not receive the early O update. No later frequency may choose eligibility or tune
O, and the split must be fixed without inspecting frequencies. This tests whether direction
evidence transfers to association prediction while avoiding use of the same frequencies for both
selection and validation. It remains vulnerable to forecast aging, so report it separately from the
primary frequency-free endpoint and against the causal reference.

## Leakage and alignment gates

The DS8 alignment diagnostic may describe why later forecast agreement collapses, but held
alignment cannot gate this experiment. Any eligibility or maximum-age rule must be selected from
training/calibration reception metadata and then applied unchanged. A record with poor held
frequency alignment stays in the primary frequency-free direction score. In the secondary later
frequency endpoint it contributes its proper density, including failure; it is not dropped.

Fit nuisance terms, mark densities, occupancy, response slope/bandwidth and any temporal state only
on calibration reception. Physically remove calibration held rows and every evaluation/DS8 row
before feature scaling or fitting. Candidate disagreement and crossing-support summaries may use
forecast covariates from a scored record because they do not use observations, but they must not
alter the primary population after the rule is frozen. Bind exact source-window IDs, candidate
weights, TLE/pose digests, feature arrays and role assignments in the receipt.

## Bounded implementation and decision rule

First implement a read-only design audit that exports candidate crossing order, zero brackets,
schedule support and disagreement without detector outcomes. Stop if essentially no lanes contain
material competing candidates with different predicted orders; the corpus then cannot answer an
association-specific full-crossing order-sign question under this candidate bank. This restriction
does not rule out partial-arc geometry or candidate-specific crossing-time differences.

If support exists, implement one calibration-only fit and frozen replay using the existing
candidate-set/presence likelihood. Require synthetic tests for exact P/U/O nesting, receiver-swap
sign, time reversal, candidate permutation, empty sets, candidate ordering, causal score-before-
update behavior, and independence from all frequency values in the primary outcome. Bound each
stage to 300 seconds, one numerical thread and 4 GiB, with no RF collection, IQ reprocessing or
QNAP writes.

Promote no direction claim unless O beats U and every control on the same held population, the
candidate-permutation and disagreement-stratum results show candidate-specific information, and the
effect transfers across recording clusters. Even then use the wording “signed nominal receiver
geometry improved predictive association under the frozen candidate model.” Reserve “RX0 before
RX1 for satellite X” for a future experiment with calibrated antenna response, verified receiver
mapping and independent identity truth.
