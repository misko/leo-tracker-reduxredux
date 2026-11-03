# Reproduction commands

```sh
base=reports/2026_09_30_native_adaptive_deployment/tracking/dense-source-workspace-research
bash "$base/build.sh" host view /var/tmp/leo-dense-source-final-host-view
bash "$base/build.sh" host candidate /var/tmp/leo-dense-source-final-host-candidate
bash "$base/build.sh" sanitize candidate /var/tmp/leo-dense-source-final-sanitize-candidate
bash "$base/build.sh" arm view /var/tmp/leo-dense-source-final-arm-view
bash "$base/build.sh" arm candidate /var/tmp/leo-dense-source-final-arm-candidate
bash "$base/build.sh" host sidecar /var/tmp/leo-dense-source-sidecar-host

/var/tmp/leo-dense-source-final-host-candidate/test-dense-source-workspace
ASAN_OPTIONS=detect_leaks=1 /var/tmp/leo-dense-source-final-sanitize-candidate/test-dense-source-workspace
ASAN_OPTIONS=detect_leaks=1 /var/tmp/leo-dense-source-final-sanitize-candidate/tracking \
  reports/2026_09_30_native_adaptive_deployment/tracking/candidates.tsv

python3 "$base/compare_prefixes.py" \
  reports/2026_09_30_native_adaptive_deployment/tracking/candidates.tsv \
  /var/tmp/leo-dense-source-final-host-view/tracking \
  /var/tmp/leo-dense-source-final-host-candidate/tracking \
  "$base/prefix-parity.json" /var/tmp/leo-dense-source-prefix-v1/prefix.tsv \
  --wall-limit 180

python3 "$base/compare_prefixes.py" \
  reports/2026_09_30_native_adaptive_deployment/tracking/candidates.tsv \
  /var/tmp/leo-dense-source-final-host-candidate/tracking \
  /var/tmp/leo-dense-source-sidecar-host/tracking \
  "$base/sidecar-prefix-parity.json" \
  /var/tmp/leo-dense-source-sidecar-prefix/prefix.tsv --wall-limit 180

/var/tmp/leo-dense-source-final-host-view/prefix \
  reports/2026_09_30_native_adaptive_deployment/tracking/candidates.tsv \
  5 100663296 --tail-two
/var/tmp/leo-dense-source-final-host-candidate/prefix \
  reports/2026_09_30_native_adaptive_deployment/tracking/candidates.tsv \
  5 100663296 --tail-two
```

The retained host timing ran the final two commands in the order view,
candidate, candidate, view, view, candidate. The allocation probes are
report-local builds of `control_profile.cpp`, `view_profile.cpp`,
`candidate_profile.cpp`, and `candidate_binding_profile.cpp` linked with
`group_probe.cpp`; the probe only counts global allocations while its explicit
scope is active.
