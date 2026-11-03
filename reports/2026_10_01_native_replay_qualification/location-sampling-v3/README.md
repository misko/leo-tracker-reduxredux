# Bounded location CPU sampling

`tools/native_cpu_sample.c` uses a thread-specific software CPU-clock perf
event at 199 Hz, with a 60-second child alarm. It requires no firmware or
kernel-configuration change. It samples only the child's main thread; use a
single-worker diagnostic. Its ring-reader wrap and CLI checks have a
component-owned test in `tests/native_adaptive/bench/test_cpu_sample.py`.

The first process-wide inherited-event attempt (`../location-sampling-v1/`)
failed at mmap with EINVAL and killed/reaped its stopped child. A thread-specific
event succeeded in `../location-sampling-v2/`: 11,860 samples, zero lost,
on the existing PGO executable. Symbol-level attribution put about 79% in
`leo_score_partition` and 12% in horizon construction.

For source-level attribution, the same checked source/profile and flags were
rebuilt with `-g`. That changed generated text, so its addresses were **not**
applied to the original run. This directory records a separate profile of the
debug executable, retained as `leo-location-debug`: 11,862 samples, zero lost.
`maps.txt` records the actual PIE load address. `profile.json` uses ARM
`addr2line -f -C` on this executable after subtracting that load address.

Both runs intentionally ended with child status 142 after 60 seconds. Their
completed search-point prefixes match the qualified ARM trace exactly; see
`partial-comparison.json`. Neither is a completed-search, two-worker timing,
or sustained-throughput qualification. Sampling percentages are diagnostic
observations with optimized/inlined source attribution, not precise stage
timings. No optimization was deployed as a result of this profile yet.

The debug profile attributes 2,880 samples to `cannot_win`, 1,827 to stencil
interpolation, 1,388 to horizon queries, and 712 to `isfinite`. The next
investigation is redundant interpolation validation under the explicitly
immutable, bounded orbit session; retain ordinary API checks and verify all
results before accepting any fast path. Warm-start satellite-ID lookup had
only 63 samples, so it is a lower-priority target.
