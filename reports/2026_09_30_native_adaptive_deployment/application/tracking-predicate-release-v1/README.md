# Tracking predicate application release v1

This release composes the qualified residual-predicate tracking source into the
portable application without changing application, online, scanner, detector,
or scientific configuration source. The coherent base is
`/var/tmp/leo-live-profiled-companion-source-v1.pcYnxN`; its online header is
SHA-256 `31e76a3b8d07ff21eeaf2dc0d5f9a39ffcf5bc70c1f5e185760103df86a7f8e8`.
`source-delta.json` verifies that the 289-file frozen source closure differs
from that base in exactly three files: the production `tracking.cpp`, its build
script, and the new focused residual-predicate test.

All online archives were rebuilt from source. `online-archive-members.txt`
shows the same seven direct members for host, sanitizer, and ARM, with no
`base-*` member. `LEO_ONLINE_BASE_LIBRARY` was explicitly unset. Frozen scanner
inputs are retained under `scanner-input-{host,sanitize,arm}` so the portable
application builds do not depend on mutable `/tmp` artifacts.

Host and ASAN/UBSAN tracking, online, live-core, portable-CLI, and capabilities
checks pass. ARM tracking, online, and portable application artifacts
cross-build. Root's subsequent CPU-only physical unit and CLI tests also pass,
and the installed capability output matches the host receipt. `deployment.json`
records the atomic installation as `applications/2a01927d03040337`, retaining
`applications/4f4389d74a3aed2b` as the previous release. That step enabled no RF
or autostart and left the experimental exact-score cache disabled.

The full host saved-event replay passes with 11,747 accepted observations, 64
matched tracks, weighted MSE `64906.771460780015`, and no queue drops, history
evictions, or publication failures. Its `qualified=true` value applies only to
the coalesced saved projected-event replay. The run is not a continuous
freshness qualification, and its 299.8-second source span does not exercise a
full 600-second evidence window.

The first parallel build attempts are retained in `build-online-{host,
sanitize,arm}.log`. They failed before producing artifacts because the shared
`/tmp` tmpfs was 95 percent full. The successful reruns used `compiler-tmp`
inside this report and are recorded as `build-online-*-rerun.log`. Likewise,
`build-paced-host.log` preserves the rejected wrong-schema projection probe;
the authoritative successful result is `replay-full-host.json`.

From this report directory, reproduce the source builds with:

```sh
mkdir -p compiler-tmp
unset LEO_ONLINE_BASE_LIBRARY
TMPDIR="$PWD/compiler-tmp" frozen-closure/native/adaptive/tracking/build.sh host "$PWD/build-tracking-host"
TMPDIR="$PWD/compiler-tmp" frozen-closure/native/adaptive/tracking/build.sh sanitize "$PWD/build-tracking-sanitize"
TMPDIR="$PWD/compiler-tmp" frozen-closure/native/adaptive/tracking/build.sh arm "$PWD/build-tracking-arm"
TMPDIR="$PWD/compiler-tmp" frozen-closure/native/adaptive/online/build.sh host "$PWD/build-online-host"
TMPDIR="$PWD/compiler-tmp" frozen-closure/native/adaptive/online/build.sh sanitize "$PWD/build-online-sanitize"
TMPDIR="$PWD/compiler-tmp" frozen-closure/native/adaptive/online/build.sh arm "$PWD/build-online-arm"
```

Reproduce the portable application builds with the frozen scanner inputs:

```sh
LEO_SCANNER_BUILD="$PWD/scanner-input-host" LEO_ONLINE_LIBRARY="$PWD/build-online-host" \
  TMPDIR="$PWD/compiler-tmp" frozen-closure/native/adaptive/application/build-live.sh \
  host "$PWD/build-live-host"
LEO_SCANNER_BUILD="$PWD/scanner-input-sanitize" LEO_ONLINE_LIBRARY="$PWD/build-online-sanitize" \
  TMPDIR="$PWD/compiler-tmp" frozen-closure/native/adaptive/application/build-live.sh \
  sanitize "$PWD/build-live-sanitize"
LEO_SCANNER_BUILD="$PWD/scanner-input-arm" LEO_ONLINE_LIBRARY="$PWD/build-online-arm" \
  TMPDIR="$PWD/compiler-tmp" frozen-closure/native/adaptive/application/build-live.sh \
  arm "$PWD/build-live-arm"
```

Build the saved-event harness and reproduce the full host science gate with:

```sh
projection="$PWD/frozen-closure/reports/2026_09_30_native_adaptive_deployment/runtime/leo-ingest-ds9.tsv"
LEO_ONLINE_LIBRARY="$PWD/build-online-host" LEO_DS9_PROJECTION_INPUT="$projection" \
  LEO_PACED_SCALE=0.01 TMPDIR="$PWD/compiler-tmp" \
  frozen-closure/tests/native_adaptive/application/build_paced_analysis.sh \
  host "$PWD/build-paced-host"
"$PWD/build-paced-host/test-paced-analysis" \
  "$projection" \
  "$PWD/frozen-closure/reports/2026_09_30_native_adaptive_deployment/application/ds9-targets.tsv" \
  "$PWD/frozen-closure/reports/2026_09_30_arm_location_prototype/local/tles.txt" \
  "$PWD/frozen-closure/reports/2026_09_30_native_adaptive_deployment/application/ds9-search.tsv" \
  full-pinned-coalesced 0.01 --analysis-workers 1
```

The ARM handoff files and exact hashes are in `qualification.json` and
`artifact-hashes.txt`. The required pre-installation CPU-only physical gate ran
`test-live` and `test-live-cli`; the focused production tracking test had
already passed independently on ARM. The production executable remains beside
the matching detector shared object and its `.so.1` link.

The completed physical evidence is under `physical-arm/`; its manifest is
`physical-arm/evidence-sha256.json`. The root-owned deployment receipt binds
the installed binary and detector DSO hashes and reports unit wall time
`0.780151148` seconds and CLI wall time `0.062480161` seconds. These are
lifecycle checks, not application throughput or continuous real-time results.
