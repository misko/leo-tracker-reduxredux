# Current tracking stage profile

This report-local profiler instruments the qualified dense-sidecar production
source without changing its algorithm, public API, configuration, output or
production files. It times serial lane reconstruction stages with
`steady_clock` and emits one JSON record per stateless or stateful call.

The complete host output is the expected 676,954-byte DS9 serialization,
SHA-256 `6819cb39151bb2cbe894e5d427244aa95d1eae73e17469e5033659d2b0a30084`.
The tail-two benchmark reports two bit-exact prefixes and 64 final tracks.

For the final warm stateful 11,747-candidate prefix, measured lane work was
313.752 ms. Hough histogram accumulation and top-peak selection took 197.566 ms
(63.0%). Candidate-segment construction took 110.468 ms (35.2%). Inside that
inclusive segment time, initial and refined fits totaled 56.070 ms, residual
scans 38.442 ms, and dense source grouping 14.482 ms. Hypothesis packing,
winner selection, track assembly and retirement together were about 2.3 ms.
The persistent Hough matrix was already built, so its warm cost was negligible.

This changes the next optimization target. Residual admission and source-group
allocation were prior measured bottlenecks and are now qualified production
optimizations. On the current warm path, Hough histogram/peak work is the clear
dominant phase. A useful next experiment should target exact reuse or bounded
work reduction in that phase while preserving bin accumulation, top-peak tie
order and peel order. Further point-layout tuning cannot close the measured
gap.

The instrumented warm host benchmark was about 2% slower than the prior
unmodified sidecar mean, so these are phase proportions rather than latency
qualification.

The root-owned physical ARM run also preserved both tail prefixes exactly and
finished with 64 tracks. Its final warm stateful lane time was 14.205 seconds:
histogram accumulation and peak selection took 9.850 seconds (69.34%), while
candidate-segment construction took 4.152 seconds (29.23%). Inside the latter,
fits took 1.934 seconds, residual scans 1.652 seconds, and source grouping
0.432 seconds. The full benchmark took 95.730 seconds with 111,040 KiB peak
RSS. These instrumented values confirm that exact Hough histogram/peak work is
the next substantive target on ARM. No RF action was taken.

Reproduce from the repository root:

```sh
bash reports/2026_09_30_native_adaptive_deployment/tracking/current-stage-profile-v1/build.sh \
  host /var/tmp/leo-tracking-current-stage-profile-host
/var/tmp/leo-tracking-current-stage-profile-host/leo-tracking-prefix-stage-profile \
  reports/2026_09_30_native_adaptive_deployment/tracking/candidates.tsv \
  5 100663296 --tail-two
```
