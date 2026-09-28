# Boundary-conditioned fallback experiment

This bounded experiment starts from the fine-direct GLRT build and invokes the
original conditioned frequency screen only when the first GLRT residual lies
within 1000 Hz of either alias boundary, `+/-1/(2*SYMBOL_S)`. The decision uses
the residual returned by GLRT directly. It does not use an oracle, candidate
margin, or verification ranking.

For a flagged candidate, the conditioned grid is exactly
`max(-400000, fine_cfo-2000)` through `min(400000, fine_cfo+2000)` in 100 Hz
steps, with the clipped stop appended when the last interval is nonregular.
The FP32 screen and `128*FLT_EPSILON` near-maximum FP64 rechecks match the
original conditioned implementation. GLRT then runs again at that winner.
All eight proposal entries, their order, and their coarse/fine metadata remain
present. Verification fields stay null. Conditioned CFO and score are present
only when `conditioned_fallback` is true.

The threshold was selected after inspecting the 704-dwell corpus: all 3370
positive same-proposal alias mismatches were within the threshold, while 9477
of 123904 candidate outputs (7.65%) met it. Consequently the 704 corpus and its
640-dwell subset are tuning data, not a holdout. The completed run recovered
19,576/19,581 original hits; the separate four-dwell ARM run recovered 119/119
and measured 25.084860 CPU seconds/dwell, 1.32218x faster than the latest exact
cache baseline. See `REPORT.md` for per-rate counts and measurement limitations.
These results do not establish generalization to unseen data.

The first 64-dwell qualification (1408 windows) retained 1669/1669 reference hits across all
691 positive windows and added one unmatched positive. It invoked 854
fallbacks among 11264 candidates. The independent path audit found exact final
computed fields versus the full baseline for every fallback and versus the
fine-direct baseline for every nonfallback.

`build.py` produces normal host, sanitizer host, or ARM binaries. The unit
covers every supported rate with partial, full, and zero inputs; exact GLRT
parity at the returned CFO; the clipped nonregular conditioned endpoint; and
both residual signs at zero, one, two, and three GLRT-bin distances from the
boundary. Zero through two bins trigger and three bins do not.

Archived builds:

- `builds/host-cohort-v1`: exact source and binary receipts used for the root-owned
  64/704 cohort runs.
- `builds/host-final-v2`: identical algorithm/output source with the stronger
  fallback-specific unit.
- `builds/host-asan-v1`: sanitizer build; unit passed.
- `builds/arm-v1`: ARM build whose all-rate unit passed on the device.

Conditioned work is accumulated only in `conditioned_cpu_ms`. Each first or
second GLRT invocation is timed separately into `glrt_cpu_ms`, so stage times
do not overlap. `acquisition_cpu_ms` ends before the initial GLRT and therefore
excludes the post-GLRT conditioned fallback. `total_cpu_ms` includes both
operations. This pipeline preserves the approximate fine-direct proposal order;
it does not restore the full verification-ranked order. The path audit also
verified that `conditioned_score` is real only for fallback candidates.
