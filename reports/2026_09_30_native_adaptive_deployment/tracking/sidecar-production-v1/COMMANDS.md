# Reproduction commands

Run from the repository root with task-specific compiler temporary storage:

```sh
TMPDIR=/var/tmp/leo-tracking-sidecar-compiler-tmp \
  bash native/adaptive/tracking/build.sh host \
  /var/tmp/leo-tracking-sidecar-production-host
TMPDIR=/var/tmp/leo-tracking-sidecar-sanitize-tmp \
  bash native/adaptive/tracking/build.sh sanitize \
  /var/tmp/leo-tracking-sidecar-production-sanitize
TMPDIR=/var/tmp/leo-tracking-sidecar-thread-tmp \
  bash native/adaptive/tracking/build.sh thread \
  /var/tmp/leo-tracking-sidecar-production-thread
TMPDIR=/var/tmp/leo-tracking-sidecar-arm-tmp \
  bash native/adaptive/tracking/build.sh arm \
  /var/tmp/leo-tracking-sidecar-production-arm

ASAN_OPTIONS=detect_leaks=1 \
  /var/tmp/leo-tracking-sidecar-production-sanitize/leo-tracking \
  reports/2026_09_30_native_adaptive_deployment/tracking/candidates.tsv

python3 \
  reports/2026_09_30_native_adaptive_deployment/tracking/dense-source-workspace-research/compare_prefixes.py \
  reports/2026_09_30_native_adaptive_deployment/tracking/candidates.tsv \
  reports/2026_09_30_native_adaptive_deployment/tracking/dense-source-workspace-research/artifacts/host/view-tracking \
  /var/tmp/leo-tracking-sidecar-production-host/leo-tracking \
  reports/2026_09_30_native_adaptive_deployment/tracking/sidecar-production-v1/host/prefix-parity.json \
  /var/tmp/leo-tracking-sidecar-production-prefix/prefix.tsv --wall-limit 180
```

The physical ARM commands use the retained binaries with the same candidates
fixture: `test_source_keys_internal`, `test_lane_execution`, and
`leo-tracking candidates.tsv`. Hardware execution is root-owned.
