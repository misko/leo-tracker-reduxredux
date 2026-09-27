# Early-symbol native point scoring agrees on tested inputs

A separate build changes only GLRT_SYMBOL_DIVERSITY from one to zero. At integer
epochs the raw guided scorer now uses the application's symbols 2..65 on every
frame. This isolates the known symbol-selection difference without changing
the frozen candidate or interpreting the failed holdout as a passing result.

The current-repository numerical checks pass 37 tests: one import-origin check
and 36 combinations of rate (2.5/5 MS/s), edge (lower/upper), input support
(noise/early-only/late-only), and acquired CFO (-400/0/+400 kHz). Checks include
RX1 at the last probe, input immutability, score tolerance 1e-5 and tracking-CFO
tolerance 1 Hz. At zero CFO the late-only pilot passes the previous diverse
scorer's margin threshold and fails the new early-only scorer's threshold at
both rates/edges, demonstrating the intended behavior difference.

All 144 saved primary-positive points across the original 64 recorded
development visits agree with the current application scorer after rounding
the supplied timing to the nearest integer. Maximum absolute differences:

| Quantity | Maximum error |
|---|---:|
| Exact score | 7.26e-8 |
| Control score | 1.27e-8 |
| Margin | 6.79e-8 |
| Tracking CFO | 2.62e-9 Hz |

The replay completed in 1.47 seconds on CPU0 with numerical threads=1. Its
source inventory stayed unchanged, raw arrays remained unchanged, and all
expected points completed. See `development_points.json` and
`point_replay_lock.json`. No additional holdout IQ was read.

Point-call CPU sums for 72 points per rate were 124.63 ms Python / 11.78 ms
native at 2.5 MS/s and 140.12 / 15.96 ms at 5 MS/s. This is a mechanism timing
check, not an end-to-end detector benchmark: proposals are supplied, conversion
and discovery are excluded, and methods were not rotated. Do not promote those
ratios as full-detector speedups.

## Execution correction

The first generated check inadvertently imported `pilot_methods.py` from the
deployment checkout through an inherited search path. Its 12 passes are not
evidence of current-repository agreement. The wrapper now loads and asserts
the current checkout before importing the native adapter; an explicit test
checks the scorer's origin. The corrected build is `libearly_local.so`, and all
37 tests plus the 144-point replay use it. The original `libearly.so` and its
build receipt remain diagnostic artifacts, not current qualified binaries.

## Remaining work

This is numerical compatibility at tested integer hypotheses, not full
algorithm equivalence. Fractional timing, blind tone removal, proposal ranking,
and early-only sensitivity still require separate evaluation. Pure-tone false
acceptance is not resolved merely by matching the application's statistic.

Next use this point scorer for fresh confirmation in a separately versioned
controller, checking both discoveries and cached hypotheses. Keep scored CFO
separate from expected physical CFO, require fresh compatible measurements,
and invalidate rejected tracks. Evaluate generated controls and original
development data before adding a bounded search over separated windows.
Discovery coverage and reference-relative extras must both improve; numerical
parity alone cannot establish that. A final candidate needs fresh disjoint
recorded validation and complete-call timing against the 10x objective.
