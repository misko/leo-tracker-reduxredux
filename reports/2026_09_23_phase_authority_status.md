# Phase-assisted association: remaining calibration and source-authority barrier

The investigated methods have not established better satellite association or
receiver position. The [frozen random CFO comparison](2026_09_23_independent_phase_v2_results.md)
gave phase 79.67 Hz versus GLRT 78.72 Hz circular RMS, with worse selected-position
error. The [geometric sensitivity audit](2026_09_23_phase_geometry_sensitivity.md)
showed that per-dwell phase/frequency nuisance fits remove almost all short-dwell
geometric phase. The remaining continuous-recording route also lacks the
independent calibration needed to distinguish receiver drift from geometry.

This is a limitation of the audited evidence, not proof that phase can never
help or that no suitable calibration exists outside these records. No production
association or navigation improvement is claimed.

## Current continuous-recording verification

The public read-only `RecordingStore` was used to inspect
`cap-20260825T010019-89c2889553e0`, stream-1, and iterate its digest-verified
timeline metadata. No IQ was read and no model was refit. The current manifest
matches the [published selection receipt](figures/2026_09_22_postfix_dual_selection/verification.json).

| Authority checked | Current evidence |
|---|---|
| Sample rate and receiver indices | 2.5 MS/s; RX0/RX1 |
| Stored samples and counter span | Both 150,000,000 samples per receiver |
| Refill continuity | All 572 transitions across 573 refills are contiguous |
| Manifest calibration entries | Empty list |
| Retained analyzed source hypotheses | One RX0 branch paired with one RX1 branch |
| Independent simultaneous second source phase | Not retained in this analyzed example |
| External differential LO/phase/group-delay calibration | Not supplied by the manifest or phase artifacts |
| August-valid RF phase-center/world-frame geometry | Not supplied by the checked-in station authorities |

The [fresh metadata audit](figures/2026_09_23_independent_phase/geometry-sensitivity/continuous-authority.json)
records the manifest hash, sample counters, and exact reader API. It reproduces
the timing result without decompressing the 60-second IQ recording.

## What the saved phase does and does not provide

The [refined pilot artifact](figures/2026_09_22_pilot_support_closure/pilot-results.json)
contains 36 probe epochs and five estimator variants: 180 observations of the
same paired-source hypothesis, not 180 independent sources. It retains receiver
phasors, frame times, carrier/reference conventions, relative CFO/rate, delay,
phase intercept, and the complex response. That is useful reproducible local
phase evidence.

Those nuisance parameters are estimated from the same IQ. The broadband
cross-products may include source mixture, and the artifacts do not contain a
second simultaneously isolated emitter with source-specific phase on the same
carrier/time reference. Consequently, they cannot directly form a two-source
difference that cancels a common receiver phase. Multiple estimator variants,
frequency bands, or receiver-side branch IDs do not supply that missing source.

For one source, the measured receiver difference contains geometric phase plus
an unknown differential receiver/channel phase. Allowing that nuisance to vary
freely absorbs the same time structure being attributed to satellite motion.
Setting it to zero, or estimating it from the target source and then treating it
as an independent calibration, would not resolve the ambiguity.

The [August topology](../deploy/station/gauss-four-path-postreboot-20260816-v1.json)
does establish electrical RX-to-LNB labels for the radio. It does not establish
RF phase-center positions, cable/slot sign, world pose, or differential phase
stability. The September nominal 8 cm fixture authority has a later validity
start and unmeasured RF fields; it cannot be backdated to this August recording.
The operator's “axis is 79deg east” observation likewise does not supply an
electrical calibration or a capture-valid directed RF baseline.

## Evidence needed to resume the geometric route

A further metadata-only check of the **full archived trajectory banks** found
concrete candidate material beyond the single pair retained in the phase report:
42 deduplicated branches across four paths, including five RX0 and fourteen RX1
branches for stream-1. Two branches on each receiver overlap the selected
31.8–32.8 s interval. The second RX0 branch overlaps both RX1 branches for
0.825 s. Within each receiver, the two branches share no canonical or raw
source-observation IDs, so they are separate archived hypotheses, not simply
two alias entries of the same archived branch. This still does not prove two
physical emitters.

The [full inventory](figures/2026_09_23_independent_phase/geometry-sensitivity/continuous-branch-inventory.json)
and [metadata-only builder](figures/2026_09_23_independent_phase/geometry-sensitivity/build_continuous_branch_inventory.py)
preserve complete IDs, support intervals, source-product digests, and phase
qualification counts. The secondary RX1 branch has zero archived qualified
75 ms phase windows. Source matching and known-pilot isolation must therefore
be established before treating it as a second phase source. Raw source IDs are
path-local; an equal ID across receivers can merely mean equal sample-start,
candidate-rank, and method labels. Such equality is not independent emitter
matching evidence and must not be used as a global source join.

The subsequent [probe-level audit](figures/2026_09_23_independent_phase/geometry-sensitivity/continuous-branch-discrimination.json)
checked that exact 31.8–32.625 s intersection using all archived branch-associated
candidates. It read metadata/products only; no IQ or phase holdout was opened.

| Associated probe opportunities | RX0 | RX1 |
|---|---:|---:|
| Selected branch | 31 | 33 |
| Secondary branch | 2 | 13 |
| Both branches at the same probe start | 0 | 12 |
| Ambiguous branch associations | 0 | 0 |

There are **zero probe starts with all four branches**. Consequently, the
common receiver-offset closure `(RX1 selected − RX1 secondary) −
(RX0 selected − RX0 secondary)` cannot be evaluated on these archived
opportunities. Overlapping track support intervals did not establish simultaneous
two-source support. This rules out that test on this interval's retained
detections; it does not prove that a second signal is absent from its raw IQ.

The selected RX0/RX1 branches share 30 probe starts, all passing the existing
two-sample modulo-frame timing gate. RX0 selected versus RX1 secondary shares
13 starts and none passes; RX0 secondary versus RX1 selected shares two and
both pass; the two secondary branches share none. These are local template
timing diagnostics, not verified common phase references or emitter identities.
The [reproducible builder](figures/2026_09_23_independent_phase/geometry-sensitivity/build_continuous_branch_discrimination.py)
retains every associated candidate and reports ambiguity explicitly. It does
not select an alias path, unwrap CFO across gaps, or fit a receiver drift model.

Before a two-source cancellation study, another predeclared interval/cohort or
fresh analysis of saved IQ must establish simultaneous, independently isolated
pilot support on both receivers. Any subsequent model qualification must freeze
pairing, aliases, and masks on seeded random whole-group training data and test
random held groups. Neither alternating nor chronological splits are used.
The geometric goal remains unproven, and the missing calibration is not assumed.

### Full-recording availability check

The [full-capture audit](figures/2026_09_23_independent_phase/geometry-sensitivity/full-capture-branch-quartets.json)
extends this check across the same 60-second stream-1 recording. It enumerates
the five RX0 and fourteen RX1 linear branch representatives returned by the
existing alias-deduplication helper,
requiring a unique branch-associated candidate and two different candidate ranks
within each receiver at an exact shared probe start. It finds **zero four-branch
quartets**. No other interval in these archived track-associated detections
therefore supplies the simultaneous support missing from the selected excerpt
within that representative set.
The scope audit confirms that all final trajectories are linear (10 RX0 and
29 RX1) and alias variants have identical observation membership within every
branch. Thus representative selection does not discard branch observations in
these particular banks. RX0 has zero distinct-candidate branch-pair
co-occurrences; RX1 has 14 branch pairs contributing 511 pair/probe
opportunities. Every branch association is unique.

Crucially, the underlying pilot scans retain at least two GLRT64-scored
candidates at **all 2,400 probes on each receiver**, with 2,400 common probe
starts. These are scored hypotheses, not qualified detections or independent
emitters. The zero-quartet result is therefore a limitation of the retained
trajectory associations, not absence of saved per-probe candidate material.
The next available route is phase-blind qualification of those unassociated
candidates: timing, fixed alias consistency, persistent separate support, and
cross-receiver compatibility must precede any phase-based source choice.
The [subsequent raw-candidate screen](2026_09_23_unassociated_phase_candidates.md)
finds six isolated probe opportunities with two timing-compatible component
pairs. They are candidate material for source-isolation tests, not a validated
two-source phase arc.

The [builder](figures/2026_09_23_independent_phase/geometry-sensitivity/build_full_capture_branch_quartets.py)
reads digest-verified analysis products, without opening IQ, fitting phase, or
choosing a favorable matching. This result concerns this stream and analysis
run; it does not establish absence in unassociated detections, raw IQ, the other
stream, or other recordings.

A future two-source test must retain a global capture-counter phase reference.
Coincident probe starts alone do not imply simultaneous pilot epochs. Exact
common-time measurements cancel a receiver-common term; asynchronous phases
need independently supported rate transport and propagated uncertainty.
Different carrier offsets also retain frequency-dependent receiver response,
including differential delay. Neither a mixed-signal broadband fit nor a free
per-window nuisance fit supplies independent geometric calibration. Any future
association claim must beat frozen no-geometry and wrong-pair/time controls on
seeded random whole-group holdouts. Absolute speed/direction or position remains
unverified by the present phase evidence.

For absolute geometric interpretation, the missing input is a calibration or hardware reference
authority that constrains differential receiver phase/frequency/delay over the
analysis interval, together with capture-valid RF baseline/mapping information.
A shared oscillator reference, if present, must be documented and its remaining
differential-chain behavior characterized; shared sample indices alone do not
establish that condition.

An alternative research route would require at least two independently isolated,
simultaneous source-specific phase measurements with a common receiver state and
verified timing/phase references. Such measurements are not present in this
selected example's retained phase artifacts. This audit has not established
their absence across the entire archive.

A question about saved common-signal calibration and LNB oscillator-reference
documentation was sent to the operator; the response was **“Not sure.”** The
oscillator relationship therefore remains unverified, not assumed independent
or shared. A repository search found the earlier
[dual-LNB conducted drift reference](2026_08_22_dual_lnb_drift_reference.md): it
documents separate sequential bench runs, not a simultaneous capture-bound
differential phase calibration. Its physical mapping to the current station
paths is incomplete, so it cannot supply the missing correction.

No new RF collection or hardware
change is authorized or performed here. Further association/position claims
require independent validation and the relevant authority; random whole-group holdouts remain mandatory
for any subsequent method qualification.
