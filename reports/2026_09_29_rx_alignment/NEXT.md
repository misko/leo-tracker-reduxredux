# Proposed geographic gate for differential receiver drift

The completed frequency diagnostic favors time drift on a limited subset. It
does not supply absolute Doppler calibration. A receiver difference constrains
relative drift while leaving a common drift unconstrained. Subtracting all the
correction from RX0, adding it to RX1, or splitting it between them introduces
different common-mode assumptions. Do not choose that allocation by roof error.

Before geographic execution, define a correction entirely from training data,
with target-track/pair exclusion and explicit training-only qualification.
Preserve the original independent-track model and all unmatched tracks. Where
calibration is unavailable, retain the original data and report the fallback;
do not silently extrapolate a different RF or scan's calibration. Preserve every
record in the original eighteen panels and report correction coverage by scan,
track and receiver.

A bounded sensitivity comparison should predeclare symmetric splitting and
both receiver-anchor conventions. These are assumptions to test, not three
independent calibrations or a menu from which to select the nearest coordinate.
Require exact zero-correction replay, receiver-swap symmetry, held isolation,
known-drift injections and an explicit test exposing the unidentifiable common
mode. Keep coefficient bounds and missing-calibration handling frozen before
any fits. Retain full uncertainty about pairing and calibration; do not relabel
these frequency-coherent pairs as verified satellite identities.

Only then fit on identical training observations and compare held prediction
and geographic error separately, retaining all start and audit failures.
Improvement must not be attributed to the 20-degree antenna tilt: this correction
uses paired frequency trajectories, not calibrated beam geometry or arrival order.
These previously explored datasets and their unsurveyed reference do not provide
blind accuracy validation. This geographic gate has not been implemented or
executed in the alignment report.
