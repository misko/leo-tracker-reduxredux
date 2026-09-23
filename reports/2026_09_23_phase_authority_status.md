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

The necessary next input is an existing calibration or hardware reference
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
documentation has been sent to the operator. No new RF collection or hardware
change is authorized or performed here. Further association/position claims
remain pending that authority; random whole-group holdouts remain mandatory
for any subsequent method qualification.
