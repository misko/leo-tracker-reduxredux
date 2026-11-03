# Exact Hough peel-reuse diagnostic

This report-local diagnostic measures the next exact tracking optimization
without changing production. It is based on production tracking source
`f2fb20b646287e4ef0392131a48e3dff337b14db69ef09564eae1b0439b659bc`.
Both diagnostic builds preserve the complete 64-track serialization at SHA-256
`6819cb39151bb2cbe894e5d427244aa95d1eae73e17469e5033659d2b0a30084`.

The low-overhead build separates Hough histogram accumulation from peak-cell
scanning. On the final warm host prefix, accumulation takes 208.500 ms and
peak scanning takes 32.007 ms. Accumulation is 86.69% of those two measured
phases. The per-slope clock reads add instrumentation overhead, so these values
identify proportions rather than qualify latency.

The separate counter build inventories an exact within-lane reuse design. The
first peel performs 42,300,947 additions; all current peels perform 188,771,622.
Across the later peels, 8,982 retired points dirty 13,559,683 unique cells. If
each dirty cell were rebuilt from zero by visiting its remaining contributors
in original ascending point order, those later peels would visit 22,651,471
contributors. Including the unchanged first peel gives 64,952,418 visits,
34.41% of the current additions. Peak selection would still scan all
117,997,568 cells.

The proposed exact layout is lane-local: retain one FP64 histogram, mark cells
touched by retired points using the existing forward bin matrix, and use a CSR
list whose contributor indexes are appended in ascending point order. Dirty
cells start at zero and add only still-available contributors in that order;
untouched values retain their existing bits. The existing slope/bin traversal,
peak comparator, candidate-segment order and peel order remain unchanged.

For the 3,601 by 512 grid, each lane has 1,843,712 cells. A dense FP64
histogram is 14.066 MiB, uint32 offsets are 7.033 MiB, and a byte dirty map is
1.758 MiB. Uint16 contributor indexes are safe under the existing 40,000-point
input bound. The largest measured lane needs 14.932 MiB of contributor indexes,
for 37.790 MiB lane-local scratch; the two largest concurrent lanes total
72.468 MiB. Together with the measured 88,221,442-byte persistent forward-bin
cache, two-lane payload is about 156.6 MiB before allocator metadata and other
application state. Retaining inverse indexes for all eight lanes would cost
136.95 MiB before histograms and is rejected.

The counter build itself allocates only uint16 contributor counts plus a dirty
byte map, with a measured 5,531,136-byte peak per lane. It does not implement
the CSR accelerator and its runtime is not optimization evidence.

The root-owned CPU-only ARM split-timing run passed both tail prefixes exactly
and returned 64 tracks. In the final warm lane, instrumented accumulation took
8.957 s and peak scanning took 1.720 s, so accumulation was 83.89% of those two
split phases. The final warm call took 16.192 s and its lane took 15.572 s. This
is deliberately not an uninstrumented latency baseline: the same workload took
14.806 s in the prior stage profile (and 14.744 s in the earlier sidecar run),
while this build reads clocks inside every slope. The 100.371 s whole-process
run used 111,032 KiB maximum RSS. No RF action was taken.

This evidence supports one bounded next experiment: implement the lane-local
exact CSR layout described above for at most two concurrent lanes, enforce the
measured scratch budget, and compare complete outputs against the current
implementation. It does not support retaining inverse indexes for all lanes or
promoting an optimization before exact host and ARM qualification.

Reproduce the host diagnostic from the repository root:

```sh
bash reports/2026_09_30_native_adaptive_deployment/tracking/hough-peel-reuse-diagnostic-v1/build.sh \
  host /var/tmp/leo-hough-peel-diagnostic-host
/var/tmp/leo-hough-peel-diagnostic-host/leo-tracking-prefix-stage-profile \
  reports/2026_09_30_native_adaptive_deployment/tracking/candidates.tsv \
  5 100663296 --tail-two
/var/tmp/leo-hough-peel-diagnostic-host/leo-tracking-prefix-peel-counters \
  reports/2026_09_30_native_adaptive_deployment/tracking/candidates.tsv \
  5 100663296 --tail-two
```
