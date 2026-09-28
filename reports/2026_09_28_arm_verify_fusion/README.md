# Exact verification-score fusion

This isolated experiment starts from the selected screen-rotation V1 build.
It fuses the final `acquire_score`, `verify_score`, and
`verify_control_score` traversals without removing a frame, symbol, sample, or
normalization term.

The original scorer evaluates the same CFO phasor for even-symbol acquisition,
odd-symbol exact verification, and odd-symbol control verification. Exact and
control verification also accumulate the same received-sample energy over the
same odd symbols. The fused helper computes each phasor once and shares that
odd-symbol energy. Template products remain stored before correlation, and
each result retains its original symbol, sample, frame, magnitude,
normalization, and score-addition ordering.

`test_verify_fusion.c` compares the helper against all three original calls
with exact `double` equality. It covers 2.5, 5, 7.5, and 10 MS/s; full and
minimum partial inputs; the next partial-count boundary; zero samples; three
epochs; and three CFOs. Host normal and ASAN builds execute the test during
their receipted build. The ARM executable is built but intentionally not run
locally.

The opportunity is bounded to the final verification stage for up to eight
retained candidates: it removes one third of phasor evaluations, one of the
two identical odd-symbol energy traversals, and duplicate sample traversal
overhead while preserving three independent correlation chains. It does not reduce coarse,
fine, conditioned, or GLRT work. No speedup is claimed until ARM measurement.

In the selected screen-rotation ARM probe evidence, verification consumed
77.50 ms at 2.5 MS/s, or 5.02% of the 1542.87 ms full-search CPU time. Across
the all-rate probe set it consumed 152.57, 215.96, and 275.00 ms at 5, 7.5,
and 10 MS/s, respectively, but only 3.50%, 2.44%, and 1.96% of total CPU.
Those measured stage shares bound the available end-to-end opportunity.

The initial paired 2.5-MS/s ARM probe set measured 1532.124643 ms for fusion
versus 1542.867175 ms for screen-rotation V1, a 1.0070115x full-search speedup.
Verification CPU fell from 77.503149 to 67.448625 ms. All four probe candidate
objects match. The completed ARM full-dwell acceptance measurement improves
from 33.912983 to 33.728123 s/dwell (1.00548x), preserving all 119 hits in 88
windows. See PERFORMANCE_REPORT.md for scope and limitations.

Exact source snapshots and receipts for host V1, host ASAN V1, and ARM V1 are
archived under `builds/`. Host normal and sanitizer qualification pass. The
ARM unit passes on hardware. Host64 matches all 11,264 candidate objects and
1,669/1,669 positive hits. The completed host704 cohort matches all 123,904
candidate objects and all 19,581 positive hits across 15,488 windows.
