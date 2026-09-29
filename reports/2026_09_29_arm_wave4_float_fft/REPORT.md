# FP32 final FFTs revisited on the fused pipeline

This variant narrows only the final scorer's 128/512-point FFTs. Matched dots,
spectral accumulation, ceilings and normalization remain FP64. FFTWf plans are
created lazily inside the first timed call; there is no precision fallback.

The 704-dwell mixed-rate host audit recovers 19,226/19,581 original standard
hits, with 21,505 unmatched positives, unchanged from Wave3. All 15,488 windows
and 123,904 candidate entries remain, but numerical outputs change.

Four saved 2.5 MS/s dual-RX dwells on PLUTO+ CPU0 measured 1.714276 seconds per
dwell with the fused outer timer, versus Wave3's two-run mean of 1.709724.
GLRT alone took 292.288 ms versus about 298 ms. This single run shows no
overall speed gain, so this variant is not selected or repeated. Both the
host/sanitizer component tests and physical-ARM component tests passed.

The earlier standalone experiment also had an ARM measurement in the central
subsecond REPORT.md (4.457 seconds search, 362 ms scoring); its own README's
cross-build-only status was stale. This experiment tests composition with the
current fused implementation, not a previously untested numerical idea.

The scope excludes file reads, initial workspace setup and capture; it includes
proposals, region construction, input conversion, search, and lazy FFTWf setup.
No radio activity or concurrent capture occurred.
