# Detection selection and cross-receiver epoch feasibility

First census all eleven existing position-pilot inputs: raw candidates, margin
gate rejection, projection, retained track membership, and observed receiver
states. A missing retained source track is not automatically a detector miss.
Exact/control GLRT scores are detector statistics, not calibrated RF powers.

Audit frame-epoch differences on the earliest acquisition family with distinct
available calibration/validation donors (family2, DS10 indices16/17), chosen by
the existing metadata inventory, not DS11 errors. Use the corrected causal donor
source assignments, public raw input/projection and persistent-track joins.
Labels remain inferred from training Doppler confidence≥0.90, not authenticated
IDs. Cross-RX pairs in the same observing opportunity receive a same/different
label only if both raw candidates have unique assigned physical-source owners.
Unknown or ambiguous ownership stays unknown; preserve rejected/untracked counts.

Compute signed epoch difference modulo the frame period declared by the installed
projection implementation, in microseconds. Do not infer an absolute range,
satellite ID or receiver hardware delay from this alone. Preserve sample rate,
RF, visit split and both exact/control scores. Verify original donor source hashes
and raw manifests. Export only existing metadata: no new RF or IQ reprocessing.
One child per donor, ≤90 seconds, at most three single-thread workers.

The initial deliverable is a feasibility/selection audit, not a position fit.
Any learned timing gate must be frozen on calibration training visits and tested
on the separate validation recording, with no tuning to DS11 reference errors.
Other acquisition families remain outside this initial feasibility claim.
