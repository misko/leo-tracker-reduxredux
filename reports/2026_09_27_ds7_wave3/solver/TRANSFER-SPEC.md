# DS7 frozen temporal-transfer specification

The transfer panel is the chronological eleventh group: `single-081` through
`single-088` and `group8-11`. It uses the unchanged wave-two exact baseline arm
`config/ds7/baseline-wave2-ready-v1.json`, including the same Student-t4 scale,
candidate policy, masks, starts, bounds, normalization, and 11.2 GHz canonical
RF convention.

Runs use explicit unit selectors, CPU1/BLAS1, nice 19, at most 300 seconds per
unit, and at most 900 adapter-seconds total. Ready singles may run as immutable
inputs arrive and are reused when the full group becomes ready; no duplicate
fits are permitted. No score, pose, or reference artifact may be read before
the panel is sealed. Unavailable inputs receive an explicit receipt rather than
an inferred scientific result.

The panel was selected by frozen chronological membership, not residual or
score behavior. Its purpose is to test temporal transfer before admitting any
new clock, slope, or geographic model.
