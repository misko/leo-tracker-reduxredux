# Application execution workers v1

This component slice composes the versioned scanner execution API with owned
analysis execution. The live default is a configured concurrency cap of two:
one detector worker and one analysis worker. Explicit layouts are limited to
four workers in each pool, and their sum may not exceed the declared CPU lane
cap. These values do not set CPU affinity or reserve cores.

The CLI validates the complete budget before loading templates, constructing a
detector, creating a provider, or touching a radio. It constructs independent
detector contexts sequentially, preflights compatible capabilities, and binds
each context with the same caller attestation over the analysis digest, exact
template bytes, control template bytes, sample rate, and detector mode. Partial
construction and every later exit destroy the contexts. The scanner always
uses `leo_scanner_run_timed_ex`, including the one-worker case.

`AnalysisConfig::analysis_workers` owns the tracking executor. One keeps the
existing serial path and permits an existing external port. Two through four
bind an owned port and reject an external one. The executor is constructed
before `Session` and destroyed after it.

Host and ASAN/UBSAN component tests passed. They cover defaults, invalid and
oversubscribed budgets before side effects, partial construction cleanup,
incompatible process-serialized capability rejection, distinct context
bindings, template-sensitive attestations, owned worker lifetime, and the
external-port conflict. The ARM application and both tests cross-compiled but
have not been executed by this receipt. No device or RF was used.

The frozen pre-support-port source closure is recorded in
`source-manifest.json`. It intentionally binds the Session ABI at the time of
this build so later additive Session work cannot silently change these
artifacts. The build products are under `build-host`, `build-sanitize`, and
`build-arm`; `qualification.json` records their hashes and dependency hashes.
`source-snapshot.tar.gz` preserves all 179 source/build files from this frozen
composition; its digest is recorded in `deployment.json`. Extract it separately
when reproducing the pre-support-port ABI, and use the pinned dependency
archives and DS9 input files described by the receipts.

Reproduce the three builds from the repository root with:

```sh
base=reports/2026_09_30_native_adaptive_deployment/application/execution-workers-v1
LEO_SCANNER_BUILD="$PWD/reports/2026_09_30_native_adaptive_deployment/scanner/context-execution-v1/build-host" \
LEO_ONLINE_LIBRARY=/tmp/leo-online-dispatch-fix-host \
native/adaptive/application/build-live.sh host "$base/build-host"
LEO_SCANNER_BUILD=/tmp/leo-scanner-live-workers-sanitize \
LEO_ONLINE_LIBRARY=/tmp/leo-online-dispatch-fix-sanitize \
native/adaptive/application/build-live.sh sanitize "$base/build-sanitize"
LEO_SCANNER_BUILD=/tmp/leo-scanner-live-workers-arm \
LEO_ONLINE_LIBRARY=/tmp/leo-online-dispatch-fix-arm \
native/adaptive/application/build-live.sh arm "$base/build-arm"
```

Saved-candidate 1/2/4-worker parity, physical ARM component execution, and live
deployment are separate qualification steps. This receipt makes no RF,
real-time, hardware, or scientific-recovery claim.

## Subsequent physical qualification and deployment

`deployment.json` records root's subsequent PLUTO+ unit/CLI passes, saved-event
replay, and atomic installation of release `b7b2d5c6e3f95ecd`. The original
qualification receipt above remains the frozen build receipt. Host replay at
1/2/4 workers and ASAN/UBSAN replay at two workers preserve all 11,747 accepted
observations, 64 tracks and the reference score without drops. Physical replay
at one/two workers produces exactly equal scores between those configurations,
within the pre-existing reference tolerance.

The physical replay delivers the 299.802-second recording in 59.964 seconds.
Publication time falls from 27.978 to 16.003 seconds; completion after the
producer stops falls from 53.002 to 41.019 seconds. This single measured pair
shows a 1.75x publication speedup, not continuous real-time qualification.
Replay uses saved projected events and has no detector worker. Two analysis
workers therefore consume both PLUTO+ compute lanes; the live default remains
one detector plus one analysis worker. No new RF or autostart was enabled.
