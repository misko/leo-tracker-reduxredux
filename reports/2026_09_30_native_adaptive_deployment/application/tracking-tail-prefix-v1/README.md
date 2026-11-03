# Application tracking tail-prefix benchmark v1

This application-owned benchmark measures the exact tracking prefix-cache path
through `application::TrackingExecution`. It binds the recorded 11,747-row DS9
candidate fixture by SHA-256, sorts it by `(support_end_utc_ns, candidate_id)`,
and constructs the same 60 five-second causal prefixes used by the application
replay. Prefix 58 seeds a `tracking::Reconstructor`; prefix 59 appends the final
181 candidates. Both prefixes are also reconstructed from scratch. The
benchmark compares every result field and floating-point bit before emitting a
stable result digest.

Host and ASAN/UBSAN runs pass with one and two analysis workers. Both worker
counts produce the same seed and final result digests, 64 final tracks, and the
same prefix-cache accounting. At the final prefix the cache retains 88,551,126
payload bytes across eight lanes; all eight lanes are extended and 651,781 new
bin cells are computed. No prefix/config invalidation or capacity fallback
occurs.

The host timings are evidence for this host only. The two-worker run has a
larger process CPU total and maximum RSS because it executes lane work
concurrently. `resident_cache_bytes` is the cache's accounted payload, while
`maximum_rss_kib` is whole-process peak RSS; they are different quantities.
This is a growing-window tail benchmark. A rolling-window expiry invalidates
the exact prefix cache and requires cold reconstruction, so this receipt does
not establish sustained five-second publication or continuous real-time
operation.

Reproduce the host or sanitizer build from the repository root after building
the matching tracking archive:

```sh
native/adaptive/tracking/build.sh host /tmp/leo-tail-tracking-host
tests/native_adaptive/application/build_tracking_tail_benchmark.sh \
  host /tmp/leo-tail-app-host /tmp/leo-tail-tracking-host \
  reports/2026_09_30_native_adaptive_deployment/tracking/candidates.tsv

native/adaptive/tracking/build.sh sanitize /tmp/leo-tail-tracking-sanitize
tests/native_adaptive/application/build_tracking_tail_benchmark.sh \
  sanitize /tmp/leo-tail-app-sanitize /tmp/leo-tail-tracking-sanitize \
  reports/2026_09_30_native_adaptive_deployment/tracking/candidates.tsv
```

The frozen ARM binary is in `build-arm`. After copying it to a test directory
beside the already staged fixture, root can run the two bounded CPU-only tests:

```sh
./run-bounded 240 ./leo-application-tracking-tail-benchmark \
  ../tracking-prefix-v1/candidates.tsv 1
./run-bounded 240 ./leo-application-tracking-tail-benchmark \
  ../tracking-prefix-v1/candidates.tsv 2
```

These commands read saved candidates and do not access RF hardware. ARM
execution is pending root's physical qualification in this receipt.
