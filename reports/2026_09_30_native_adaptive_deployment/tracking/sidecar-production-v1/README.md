# Dense source workspace production qualification

Production tracking now binds each lane's immutable source-group identity to a
dense integer sidecar once and reuses lane-local selection storage across raw
and refined hypotheses. The public tracking API, configuration, persisted
identities, ranking, floating-point operations and result order are unchanged.
The promoted `tracking.cpp` is byte-identical to the physically qualified
research sidecar.

The component-owned source-group test compares the workspace with the original
owning ordered-map algorithm across explicit/fallback collisions, embedded NUL
and long keys, rank ties, duplicate indexes, empty/subset/disjoint/repeated
calls, owned split lifetime, 20,000 randomized forward/reverse selections and
two concurrent lane-local workspaces. The existing public `LaneExecution` test
still covers synchronous borrowed dispatch, ordered results, cold/extended/
reused state, joined callback failures, malformed dispatch and recovery.

Host, ASAN/UBSAN and TSAN component builds pass. The complete sanitizer run on
11,747 DS9 candidates emits the expected 676,954-byte output, SHA-256
`6819cb39151bb2cbe894e5d427244aa95d1eae73e17469e5033659d2b0a30084`,
with empty stderr. All 60 causal prefixes are byte-identical to the frozen
source-key-view control.

Root-owned physical ARM tests passed: the source-group regression took 3.920
seconds wall time, the public lane-execution test took 0.130 seconds, and the
complete 11,747-candidate production CLI took 22.060 seconds and emitted the
same expected output. The preceding research ABBA measured the sidecar 2.222%
faster warm and 8.111% faster cold than the intermediate dense-ID-in-`Point`
candidate. The timing remains well above the five-second continuous
publication target; application composition and freshness are separately
qualified. No RF was used.
