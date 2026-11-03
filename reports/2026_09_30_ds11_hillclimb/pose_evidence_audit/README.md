# Capture-bound pose metadata contains no independent altitude calibration

All 32 original DS11 captures have pose companions. Each companion passes its
content digest, authority digest, session/manifest binding and authority
validity-interval checks. All repeat one authority digest; they are not 32
independent station measurements.

Every companion records altitude and vertical datum as unknown. Every RF
phase-center baseline is unknown. Receiver elevations are unknown and both
physical-to-software receiver mappings are provisional. Nominal mount geometry
and east/west azimuth statements do not supply those missing measurements.

This verifies that the missing calibration is present in the capture-bound
evidence as well as the current repository configuration. It does not prove
physical installation continuity or surveyed horizontal truth. No location,
height, phase baseline or pointing correction is inferred from the benchmark.

Two tests cover digest tampering and wrong-capture rejection. The audit reads
the documented immutable companion artifacts only; no acquisition, companion
rewrite, position fit or QNAP mutation occurs. All paths and digests are retained
in [outcome.json](outcome.json).

An independently measured antenna altitude with its datum is still needed to
evaluate a defensible fixed-height correction. Calibrated RF phase-center
geometry or an independently calibrated receiver-frequency record would
support different physical approaches; this metadata does not provide them.
The already failed free-height fit must not be used as substitute calibration.
