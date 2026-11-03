# Rejected separated-loop CI16 prefix reuse

This variant uses the same exact-prefix proof and owner attestation as
`../ci16-window-energy-v1/`, but moves the choice between direct summation and
prefix reuse outside the per-sample loop. The changed source is retained here.

All scientific fields match both the control and the saved DS9 reference.
Mean detector-call CPU is 103.009063 ms for control versus 102.935011 ms for
the prototype, only 0.072% lower. Whole-process CPU is effectively unchanged.
Reject this variant: the additional private state and fast path are not
justified by a useful measured saving. Production sources are restored, and
the experiment does not replace any full-scan or sustained-cadence result.
