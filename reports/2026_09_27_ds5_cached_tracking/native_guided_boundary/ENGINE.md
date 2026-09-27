# Guided support-boundary engine

The frozen V3 guided API rejects a caller before scoring when
`abs(expected_physical_cfo_hz - scored_cfo_hz)` exceeds the GLRT residual
support `0.5 / 4.4 us`. A current analyzer coordinate exceeded that mathematical
boundary by about `2.8e-9 Hz` through floating-point reproduction.

This isolated engine adds a fixed `1e-6 Hz` guard to that one comparison. It
does not change either supplied CFO. It calls the same V2 full-aperture scorer
as frozen V3 and reconstructs the same V3 status rule from the fresh result:
`physical_innovation = tracking_cfo_hz - expected_physical_cfo_hz`, with the
unchanged strict 8 kHz reacquisition threshold. Blind acquisition, ranking,
nuisance conditioning, templates, timing, scoring and observation mapping are
the frozen TG11 implementation.

`NativeGuidedBoundary` has the same constructor shape, context lifecycle, and
`screen`, `blind`, and `guided` contracts as `NativeTG11`. The binary exports
the guard value for loader attestation. This is a research numerical-boundary
candidate, not a production or persisted-contract change.

No saved IQ is evaluated by the component suite. A separate frozen protocol
must determine whether the formerly rejected real coordinate scores and passes
the unchanged scientific gates.
