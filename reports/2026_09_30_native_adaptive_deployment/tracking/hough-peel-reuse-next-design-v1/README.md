# Exact Hough reuse: bounded attribution and next design

This read-only follow-up explains why the exact CSR experiment was rejected and
identifies a smaller exact design worth considering. Production is unchanged.

Linux performance counters were unavailable (`perf_event_paranoid=4`), so the
bounded attribution used GCC `-pg` builds of the frozen control and rejected
CSR candidate on the same two final causal prefixes. The profile is coarse
(10 ms samples) and changes code layout; it is useful only for attribution, not
latency qualification.

The CSR candidate spent 0.14 sampled seconds in eight
`ExactPeelHistogram` constructors, 17.5 ms per lane. Its final warm call took
0.944 s under `-pg`, so inverse construction was about 15% of that call rather
than the dominant cost. `reconstruct_lane` self time was 1.17 s across the
combined candidate workload versus 0.84 s for the control. The dominant
regression therefore remains in the inlined dense-cell/dirty-rebuild path and
its cache behavior. This agrees with the qualified non-profiled result: CSR
stateful work was 2.71x slower despite exact output.

The smallest next exact design is a dense histogram with a dirty-byte map and
no inverse index:

1. On the first peel, accumulate the dense slope-major histogram in the
   existing slope/ascending-point order.
2. After selecting and retiring a track, use the existing forward bin matrix
   to mark each affected cell dirty and set that cell to zero once.
3. On the next peel, retain the existing slope/ascending-point traversal. Add a
   point's weight only when its cell is dirty. This rebuilds every dirty bin
   from zero in the exact original contributor order.
4. Clear dirty flags during the unchanged full 512-bin peak scan. Untouched
   histogram cells retain their exact bits; peak, hypothesis and peel order do
   not change.

This removes CSR construction and indirect contributor reads. It still makes
all 188,771,622 measured forward-bin visits, but reduces histogram additions
from 188,771,622 to the previously measured exact 64,952,418 and avoids most
per-peel zeroing. It adds 32.35 million retirement bin lookups and a dirty test
on later-peel point visits. These counts make a substantive gain plausible but
do not prove one.

Memory is bounded and lane-local. A lane needs 14,749,696 bytes for the dense
FP64 histogram, 1,843,712 bytes for dirty flags, and at most 17,392 bytes for
the measured point-to-chunk lookup, replacing the existing 4,096-byte slope
buffer. The two largest measured lanes add 33,209,784 bytes (31.67 MiB). With
the existing 88,221,442-byte forward cache, the combined two-lane payload is
about 115.81 MiB before other application state and allocator overhead.

No implementation is included here. A future isolated experiment should be
attempted only with the same exact adversarial and all-prefix comparisons used
for CSR, separate allocation instrumentation, and a host performance gate
before any ARM build.
