# Bounded offline analysis for ten-minute scan starts

The recovered fixed native-10M scanner exposed an analysis throughput problem:
the complete refinement, per-visit analysis and tracking cycle took more than
ten minutes with two analysis workers, followed by a one-minute timer delay.
Two observed cycles took 10:06.582 and 10:46.041. This would gradually accumulate
pending recordings on the requested ten-minute acquisition cadence.

Release `2bb4c3b1ec806b7c9181ff577a1c87387331f604` adds a bounded runtime setting
for fixed per-visit analysis, accepting one through four workers with the existing
two-worker default. The backfill CLI exposes `--fixed-maximum-workers`; adaptive
legacy analysis still uses its existing two-worker bound. Analysis configuration,
probe stride, detection thresholds, storage contracts and scientific products
are unchanged. No golden fixture was edited.

## Validation

29 CLI and scanner component tests passed. New checks compare serial and parallel
native single-RX product rows for RX0 and RX1, preserve chronological output and
reject inexact or out-of-bounds worker settings before reading IQ or launching
jobs. A later 100-test run also covered both Pluto adapters and the host worker.

Read-only replay of saved recordings compared complete scientific products at
two, three and four workers. All compared products match exactly. Four-worker
timing after warmup on one eight-visit chunk was:

| Receiver | Two workers | Four workers | Wall-time reduction |
| --- | ---: | ---: | ---: |
| RX0 | 5.516 s | 3.611 s | 34.55% |
| RX1 | 5.347 s | 3.472 s | 35.06% |

The six two-versus-three comparisons and the four-worker comparisons are retained
with source session identities in the JSON evidence. This benchmark uses the
development interpreter and demonstrates exact parity plus relative throughput;
the deployed full-cycle measurement is the operational acceptance check.

## Deployment and rollback

The immutable release was staged through `stage-production-release` using system
Python 3.14. The source tree, runtime and release metadata checks passed. Web assets
built successfully; the main JavaScript and CSS asset names remain unchanged.

Only `/etc/systemd/system/leo-persistent-hop-analysis.service.d/50-analysis-release.conf`
was changed. It selects the new release and `--fixed-maximum-workers 4`, retaining
the low-priority service, one-thread math-library settings and all existing jobs.
The prior drop-in is preserved at
`/etc/leo/analysis-cadence-recovery-20260913/50-analysis-release.conf.before`.
The already-running analysis cycle was allowed to finish before the new release
started at **18:09:05 UTC**. No receive session was interrupted.

Rollback consists of restoring that saved drop-in, reloading systemd and allowing
the current analysis job to finish before the next activation. Historical products
and resumable scientific configuration remain compatible.

Acquisition remains release `1212242843055e7e4079143ab1940532e8ac76fd`, native
10 MS/s, one physical RX from radio `104000bac4950008230026001b440a003a`, with
300-second recordings on ten-minute UTC slots. This change does not activate
the unreleased adaptive host-feedback profile.

## Completed operational verification

The first four-worker backfill cycle exited successfully at **18:16:48 UTC**:
**463.408 seconds (7 minutes 43 seconds)** for the entire refinement, analysis
and tracking cycle. Systemd reported a 928.9 MiB memory peak. Including the
unchanged one-minute timer pause gives approximately 523.408 seconds between
starts, leaving **76.592 seconds of headroom** within the ten-minute cadence.
The next cycle started normally at 18:17:48 UTC.

All 2,386 visits in `scan-hop-4f91ab207c93d3ac` completed native-rate analysis at
18:15:15.414835 UTC. A real Chromium session selected this recording and loaded
coverage, GLRT64-versus-time and CFO-versus-time tabs successfully, with no
JavaScript errors. Browser evidence and a screenshot are retained alongside the
API session snapshot and the service completion journal.

The concurrent 18:10 recording, `scan-hop-2ebfe93cbfcbe163`, published 2,386 visits
at **95.4138% valid duty**, with attested continuity, successful restoration and
a qualified capture. The 18:00 scan was also qualified at 95.4048%. These are
normal scheduled production recordings, not extra RF qualification collections.

This verifies one complete faster analysis cycle while acquisition continues.
It does not establish perpetual queue stability or qualify adaptive RF feedback.
