# Phase-geometry observability audit

This audit finds useful local dual-receiver phase evidence, but no currently
identifiable geometric direction, velocity, satellite position, or named
satellite association. It does not change a production estimator, collect RF,
or reinterpret the existing phase results as geometric measurements.

## What survives the present extraction

The frozen multirate visit documents retain more than a plot. For example,
`scan-fw-9b88653c7a012fc2/visit-758.json` retains the two-channel IQ shape,
sample rate, `production_relative_phase` reference sample and fitted relative
CFO/delay, the sparse complex `normalized_model.channel_transfer`, local
time/phase arrays, frequency-held-out rows, and curve fits. The `raw_phase_rad`
arrays also exist in the per-visit evidence. This supports a reproducible local
RX1 times conjugate RX0 coherence calculation.

It does not preserve an absolute interferometric reference. The broadband fit
estimates a dwell-specific phase, CFO, CFO rate, fractional delay, and complex
frequency response. The phase tracker derotates RX1 with the fitted CFO/rate and
correlates against the fitted response. The presentation likewise gives every
dwell its own reference. These are appropriate operations for common-waveform
evidence, but a constant geometric phase can enter the response/phase intercept
and a geometric slope can enter the fitted relative CFO/rate. The established
V2 contract therefore correctly states `phase_continuity_across_retunes: false`,
`association_uses_phase: false`, `aliases_resolved: false`, and a modulo-pi
pilot ambiguity.

The current first/second-time-half implementation must also not be described as
the requested validation. It is historical development evidence. A new geometry
analysis must use the seeded random *groups* below; a block and every FFT/window
sample that contributes to it belong to exactly one group.

## Geometry and orbit authority actually available

The only capture-relevant geometry authority is
`src/leo/station/gauss-r21-lt3d-001a-20260920-v1.json`. It records nominal
fixture mount-reference positions at x = -0.04 and +0.04 m, hence an 8 cm
mechanical slot separation. Both `rf_phase_center_position_m` and
`rf_boresight_unit` are null; RX-to-slot assignments are provisional; the
fixture-local coordinates have no measured world orientation. The rotation log
adds a conservative movement exclusion and completion time, but no rotation
axis, world azimuth, cable trace, or electrical phase calibration. A mechanical
baseline is not an RF phase-center baseline.

The repository can propagate catalogue/TLE geometry and Doppler, and has a
candidate-only joint frequency-calibration contract. It explicitly retains the
receiver-frequency gauge as an eligibility condition, cross-satellite
covariance, source-span non-overlap, and `identity_claimed: false` /
`navigation_fix_claimed: false`. Existing association evidence also remains
candidate-only. Thus it is useful as an external predicted-direction/candidate
input after an authority is frozen, but is not a source identity or an
independent phase calibration.

## Identifiable quantities

For a calibrated electrical baseline `b`, a selected phase branch, and known
RF frequency, the leading model is

```
phi_10 = (2 pi f / c) b dot u + psi_10(f, t)   (mod 2 pi)
f_phase = (f / c R) b^T (I - u u^T) v_rel + d psi_10 / (2 pi dt).
```

The first expression gives one baseline projection of direction: a cone with
integer spatial wraps. It does not give azimuth, elevation, range, or absolute
position. With a fixed calibrated baseline, the rate gives one tangent-plane
velocity projection. Per-receiver Doppler gives `u dot v_rel` only after
transmit-frequency, receiver-LO, alias, timing, and clock terms are constrained.
Together these give at most two velocity projections at one instant. Total speed
and the remaining transverse component require a nonparallel baseline, a
verified dynamic arc with an orbit prior, or additional independent direction
information.

The small explicit-truth calculation in
[`results.json`](figures/2026_09_23_phase_geometry_observability/results.json)
uses an 8 cm x-baseline at 11.4403125 GHz, 500 km range, and a stated line of
sight/velocity. Its calibrated phase-plus-Doppler velocity design has rank 2
for three velocity components. When a free phase-rate nuisance is profiled, it
has rank 1. A simultaneous, frequency-matched two-source difference cancels a
common electrical phase but has rank 1 for two source direction parameters: it
only measures their projected separation. The script and its explicitly stated
truth are adjacent to the result.

## Nuisance cancellation that is valid, conditional, and unavailable

RX1 times conjugate RX0 cancels common transmitter carrier phase and most common
path Doppler for the same isolated waveform at simultaneous antennas. It does
not cancel differential LO phase/rate, cable/antenna response, receiver sample
clock effects, multipath, source mixture, spatial wraps, or a receiver mapping
error. The present large receiver-relative CFO values are therefore not
geometric phase rates.

For simultaneous separated sources `s` and `q`, a double difference can cancel
a common RX1-minus-RX0 phase only if the receiver state is shared at the
measurement epoch:

```
D_sq = phi_10,s - phi_10,q
     = (2 pi / c) [f_s b dot u_s - f_q b dot u_q]
       + [psi_10(f_s,t) - psi_10(f_q,t)].
```

It leaves frequency-dependent electrical delay unless frequencies are matched
or a separately calibrated delay model is carried with uncertainty. Exact
common-mode cancellation requires contemporaneous centers. For asynchronous
centers, transport each local phase to a common epoch with independently
measured local rates and include the propagated-rate uncertainty; this can
approximately cancel a sufficiently slowly varying LO term, but does not make
it exactly common or remove pilot ambiguity. Existing scan-1aa differences are
therefore local transported hypotheses, not calibrated cancellation evidence.
Three simultaneous sources can provide closure diagnostics, but no additional
absolute phase information.

The valuable joint-calibration opportunity is consequently modest and testable:
fit an epoch-scoped receiver-differential phase intercept, delay slope, and
possibly bounded drift from source-associated *training* arcs whose candidate
directions are externally fixed. Do not give each source/arc its own free
intercept and rate, because that makes geometry unidentifiable. A phase
calibrator must retain: unrotated complex cross-products or an exactly reversible
rotation ledger; RF center; device-counter epoch; source/isolation evidence;
baseline phase-center/world-frame authority; all CFO/response rotations; branch
sets; and calibration covariance. None may be reconstructed from a plotted
residual alone.

## Concrete seeded group-holdout validation

1. Define an atomic `phase_arc_group` before looking at geometry scores: one
   source-isolated, continuity-qualified interval bounded by retune, phase slip,
   reference change, movement-transition exclusion, or calibration-epoch change.
   All receivers, candidate branches, A/B bands, overlapping FFT windows, and
   same-source samples in that interval share its group ID. Never split a group
   merely to balance a score.
2. Build a deterministic manifest of group ID, scan ID, RF channel/edge, rate,
   rotation state, receiver mapping/calibration epoch, candidate set, and source
   isolation digest. Assign groups by a recorded seed and hash of the group ID;
   stratify at the group level by rate, channel/edge, and rotation state when
   counts permit. If a stratum has too few independent groups, declare the
   comparison unavailable. Record the full assignment before fitting.
3. Fit only on training groups: candidate selection policy, phase branch
   marginalization rule, response/LO/delay calibration, calibration covariance,
   source mixture thresholds, and any orbit correction. Inner tuning uses a
   second independently seeded group split inside training data. No held group
   may set a response mask, phase offset, rate, alias branch, or calibration
   hyperparameter.
4. Score held groups with frozen circular likelihoods, marginalizing declared
   phase/spatial/alias branches. Compare phase-augmented scoring with the exact
   same frozen Doppler-only candidate grid and candidate set. Report all groups,
   abstentions, conditional retained coverage, wrong-time groups, wrong receiver
   pairing, different-source/same-channel controls, and catalogue-direction
   permutation controls.
5. Promote a geometric contribution only if it improves held-group candidate
   ranking or held-group local CFO reconstruction over the frozen baseline, and
   the improvement survives calibration-epoch, channel, and rotation-state
   strata. Report singular values after profiling nuisance terms and sensitivity
   to baseline, RF-center, UTC-shift, and TLE errors. A training residual is not
   validation; raw phase reversal across different-day sky is not a rotation
   test.

For a within-arc numerical A-to-B check, randomly assign nonoverlapping whole
blocks across the full arc by a recorded sub-seed. Blocks whose FFT/window/filter
support crosses an assignment boundary are excluded. A may be tracking input
while B is its disjoint frequency evaluation target, but this is not a complete
held-block prediction. A genuine held-block test uses neither its A nor B data
in the fit. Arc-level calibration/candidate validation remains the primary,
leakage-resistant test.

## Minimal next evidence

The first meaningful geometric experiment is an electrical/phase-center and
world-orientation calibration with an immutable validity interval, followed by
several source-isolated, simultaneous arcs against a frozen candidate catalogue.
It should preserve a rotation ledger and use the group protocol above. Until
then, use the present phase only for phase-blind-pair confirmation, local
coherence/slip diagnostics, and conditional receiver-offset investigations.
