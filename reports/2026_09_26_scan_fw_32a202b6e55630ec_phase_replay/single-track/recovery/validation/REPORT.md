# Differential-phase recovery observability controls

## Result

The saved satellite observable alone cannot identify geometric phase separately
from differential receiver phase.  For any smooth function `q(t)`, the two
decompositions

`geometry(t) + instrument(t)`

and

`[geometry(t) + q(t)] + [instrument(t) - q(t)]`

produce exactly the same measurement.  Smoothness, tracking quality, pilot and
broadband agreement, or fitting the selected target more accurately does not
remove this ambiguity.

The numerical controls establish the narrower claims that are supportable:

* if differential instrument phase is stable, geometric **phase change** is
  recovered exactly after removing one unknown constant; absolute phase remains
  unknown;
* a simultaneous reference with independently known geometry identifies the
  time-varying instrument term and recovers the target geometry;
* unknown differential phase in the reference injection path remains as an
  equal-and-opposite bias in the recovered target phase;
* target-specific multipath is not common with the reference and remains in the
  corrected result; and
* modulo-2-pi samples on opposite sides of a gap do not determine the missing
  cycle count.

Twelve focused tests pass.  They include missing, non-finite, and mismatched
reference rejection and a target-blindness control: the inferred instrument
series is identical for two different synthetic targets because it is computed
only from the independent reference and its known geometry.  Two tests exercise
the reference prototype itself: zero/non-finite inputs are rejected or masked,
and changing target phase passes through without changing the independent
calibration inputs.

## Audit of the existing recording

A bounded read-only search covered the saved report manifests, provenance,
selection, capture audit, and phase-report Markdown/JSON.  It found no recorded
injected phase reference, reference-path measurement, antenna coordinates or
baseline, shared-LO/clock topology, cable calibration, satellite identity, or
candidate-specific geometric phase truth.  `capture-audit/source-provenance.json`
attests the dual-receiver row format, hashes, device-counter timing, and UTC
policy; it does not attest an electrical reference.  `single-track/selection.json`
contains GLRT coordinates and one receiver-to-receiver CFO branch, not an
independent calibration experiment.

Some older analysis products use fields such as `common_reference_global_sample`.
Those are common time origins chosen from the same target observations.  They
are not an external common signal and cannot break the geometry/instrument
ambiguity.  Likewise, agreement between known pilots and broadband phase shows
that the motion is shared by those estimators, but both pass through the same
receiver and propagation paths.

## What can be recovered now

The existing recording supports the combined differential phase observable and
short-horizon prediction of that observable.  If hardware stability is supplied
as an explicit assumption, phase change relative to a chosen sample is
recoverable up to a constant.  Reversible correction and add-back can preserve
the original measured trajectory, but cannot label its components as geometry
and instrument after the fact.

Absolute geometric phase, and geometric phase change without a stability
assumption, require new independent information.  A useful reference must be
simultaneous, traverse the receiver terms being calibrated, have known reference
geometry, and have a measured stable differential injection path.  Calibration
injected after an LNB cannot measure that LNB's differential drift.  A reference
that shares receiver electronics but not the target propagation path also cannot
remove target-specific multipath, antenna-direction response, or polarization
effects.

## Artifacts

The executable controls are in `observability.py`; regression coverage is in
`tests/reports/test_recovery_observability.py`.  Reproduce with the pinned report
runtime and `pytest -q tests/reports/test_recovery_observability.py`.
