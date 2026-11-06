# Rolling speed-progress audit, 2026-11-06 19:47 UTC

These are overlapping windows, using published commit timestamps to identify
retained work. They are not independently measured then-versus-now benchmark
intervals. No production optimization was deployed in these windows.

| Window | Since UTC | Retained runtime progress | Timing evidence |
| --- | --- | --- | --- |
| 2 hours | 17:47 | None | Helper, fixed-prior and BLAS trials did not qualify a new complete-worker gain. |
| 4 hours | 15:47 | Cheaper exact inclusion-control reuse, published 16:05 | DS26-0066 480.981→394.960 s; DS26-0002 247.723→245.940 s. |
| 8 hours | 11:47 | Same retained change as the 4-hour window | Other reuse, scheduling and numerical-kernel experiments were rejected or remained diagnostic. Do not count the same gain twice. |
| 12 hours | 07:47 | Immutable orbit-bank validation reuse, scalar-phase index sharing, endpoint reuse, omitted unused screening azimuth, initial branch queue, inverse workspace, and control reuse | Component and native pairs exist, but no matched 07:47-version versus current-version run establishes the net 12-hour gain. |

The control-view pairs show 86.021 s (17.88%) less wall time on the hard case
and 1.783 s (0.72%) on the short case. Complete science, both c arms, ownership,
grid/path and eight PNG bytes agree. This is not a universal improvement:
unmodified stages vary materially, and the short scan's predictive stage and
prepared recovery regress. The whole hard-scan delta is not attributable solely
to caching. See [qualification](../2026_11_06_algo07v3_control_geometry_view/README.md).

Earlier in the 12-hour window, repeated prepared initial-search means improve
7.6–8.0%; its native short-scan pair improves 0.85%. Individual screening changes
show roughly 4–13% stage improvements, and inverse workspace has small
complete-training gains. These overlap in code and timing scope; multiplying
their ratios would invent a cumulative result.

The latest direct original-ALGO07 comparison was published at 11:43:
886.905 s for the original reference bracketed by v3 at 193.899 and 152.529 s,
with exact science/artifacts. That is an observed 4.57–5.81× cumulative comparison
on one scan at that revision, not improvement achieved during the last 12 hours.
The reference interval includes research-harness checks; its worker-plus-publication
subtotal is 811.989 s. Capture, GLRT extraction and queue delay are excluded.
See [full accounting](../2026_11_06_algo07v3_reference_recovery/README.md).

The current profiling extension discovers an 8.867-second upper bound for
individual/joint control reuse and a 192.959-second numerical-recovery branch.
Neither is an implemented or measured speedup. A stable fixed-input benchmark
panel with retained timestamped versions is needed to give trustworthy rolling
end-to-end gain percentages; isolated favorable trial clocks cannot substitute.
