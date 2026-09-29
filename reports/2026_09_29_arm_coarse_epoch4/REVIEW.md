# Contiguous four-epoch coarse FP32 prototype

Physical-ARM follow-up: all component tests passed and all candidate objects
matched on the four-dwell panel. Outer CPU measured 1.759823 seconds/dwell,
versus Wave3's 1.709724 two-run mean. Coarse CPU rose to 264.034 ms from about
217 ms. Reject this sparse variant for speed; the earlier broad-grid result
was also slower. Full host704 parity and recovery remain unchanged.

This Wave 3 variant detects runs of four consecutive sparse coarse epochs and
evaluates them as NEON lanes.  Each CFO is processed separately; each lane
retains the original tap order, scalar FP64-derived denominator, FP32 inverse,
reciprocal-square-root magnitude sequence, frame order, and final support
division.  Epochs outside a complete valid run use the original kernel.

The implementation retains all candidates and the Wave 3 boundary minimum
margin of `.1`.  The build receipt records `boundary_min_margin: 0.1`; no `.15`
gate is present.

`test_coarse_epoch4` runs the old sparse kernel and the four-epoch path on the
same workspace, then requires bitwise equality of the complete coarse grid and
support array.  It covers every rate, zero input, deterministic full-range CI16
extremes, minimum partial input, full input, consecutive groups of four, and
scalar tails.  Host and sanitizer tests passed.  The ARM test is cross-built
and must run on target before timing so it exercises the NEON implementation.

The initial scripted ARM build failure was diagnosed as
`-Werror=misleading-indentation` in the new helper and its test.  The compiler
stdout was empty and stderr identified those two warnings; formatting fixes
resolved both.  The linker was not the cause.

The host 704-dwell run matched sealed Wave 3 exactly across all 123,904
candidate objects, with zero changed candidates and windows.  Its standard
audit is unchanged at 19,226 recovered hits out of 19,581 and 21,505 unmatched
positive hits.  Host timing is diagnostic only.  No ARM execution or speed
claim is included here.

## Historical precedent

`reports/2026_09_28_arm_epoch_lane` previously qualified the same arithmetic
lane orientation for the broad coarse grid.  Its pure-kernel tests were exact
for tap counts 1, 2, 3, 4, 11, 17, 22, 33, 44, and 45, and its all-rate host
grids plus ARM unit test were byte-exact.  That broad-grid implementation was
rejected because it measured about 12% slower on ARM (1,746.50 versus 1,559.84
ms/window).  The present prototype applies epoch lanes only to consecutive
runs inside the sparse five-epoch regions and preserves scalar tails, so the
historical result is strong correctness precedent but also a warning that this
layout may regress.  A bounded ARM parity test followed by timing is required;
no additional cohort is justified before that decision.
