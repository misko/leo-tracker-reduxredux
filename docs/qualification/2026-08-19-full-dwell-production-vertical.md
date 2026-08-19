# Full-dwell production vertical — 2026-08-19

This report records the first 60-second dual-Pluto production-path capture and
baseline processing run on the dedicated host. The RAID6 array was resyncing at
approximately 50 MB/s during the run, so this is deliberately a degraded-host
test. It does not yet prove the complete Starlink scientific pipeline or the
24-hour soak.

## Capture

- session: `full-dwell-20260819-001`
- profile: `starlink-ch4-lower-2p5m-60s`
- bundle: `bulk://recordings/2026/08/19/full-dwell-20260819-001`
- manifest digest:
  `sha256:1d7c384543cb2ae6b59e644f7819c1efdd0b2126923d2c56ce4e1a513f8ff489`
- two radios, two RX paths per radio, 2.5 MS/s, 60 seconds
- exactly 150,000,000 captured samples and 573 refills per radio stream
- zero gaps, overflows, missing samples, clipped samples, or constant-IQ
  refills reported on either stream
- 2,400,000,000 uncompressed bytes, 1,181,226,637 compressed bytes, 18
  independently verified IQ chunks, and two verified timelines
- the initial host-bracket calculation reported estimated start skew 1,148,700
  ns and timing uncertainty 92,301,247 ns
- phase coherence is explicitly false

The initial manifest also reported 65.35 seconds of overlap for only 60 seconds
of IQ. That result is not physically supportable: host refill/compression delay
stretched wall-clock observation, and without a device sample counter it cannot
be treated as sample-time duration. This has been recorded as a failed timing
qualification. The contract/estimator must cap overlap by sample-derived stream
duration and reflect accumulated host uncertainty before this run can count as
synchronization evidence. The raw recording remains valid and fully verified;
the affected claim is its cross-radio wall-time estimate.

The recording and both earlier hardware canaries were pinned with durable
catalog and filesystem hold evidence using `leo process pin`.

## Catalog and baseline processing

The production PostgreSQL database was migrated from empty to the single
Alembic head with `alembic check` reporting no drift. Reconciliation registered
105 committed recording bundles and reported no issues, including this bundle
which was intentionally captured before catalog registration.

Run `reprocess-03ccbed733694b82bbf36010fe03f028` queued four jobs: quality and
power for each radio stream. All four succeeded and the immutable run was
sealed and atomically promoted in approximately 27.6 seconds. Both stages
reported 150,000,000 observed samples and 100% coverage for each stream. The
catalog and CLI expose four hashed scientific products beneath:

`/srv/bulk/leo/analysis/full-dwell-20260819-001/reprocess-03ccbed733694b82bbf36010fe03f028`

This processing time is faster than the 60-second acquisition interval for the
baseline graph, even during RAID resync. It is not yet a capacity result for
the full 15-stage research graph.

## Read-only web/API check

`leo-api` served the compiled UI and production PostgreSQL-backed API on local
HTTP. Search returned the live session, permanent hold, complete capture,
100%-coverage current analysis, profile, radios, and current run ID. Detail
returned the same generation and physical recording/analysis paths. A POST to
the reprocessing-shaped project route returned HTTP 405; reprocessing remains
CLI-only.

## Remaining work

- concrete worker adapters for the whole-dwell Starlink/QAM/Doppler/control
  graph and its production processing result;
- versioned, ordinary RecordingStore ingest for the protected TEST corpus and
  real-catalog Chromium E2E;
- atomic replacement qualification with a second current run;
- processing-backlog, restart, storage-pressure, and 24-hour soak gates;
- repeat capacity tests after RAID resync completes.

## Standard whole-dwell reprocessing addendum

After the concrete Standard adapters landed, explicit run
`reprocess-6665036cd4e44304ba8e8ce08fab6568` was queued while the baseline run
remained current. All 30 jobs (15 stages for each radio stream) succeeded, the
new immutable manifest sealed, and the current pointer atomically changed to
`standard-v1`. The former baseline run and products remain inspectable.

The run published 21 distinct scientific/presentation product kinds including
bounded waterfall, candidate coverage/cloud/tracks/refinement, Doppler, locked
integration, QAM, controls, optional-TLE status, overlays, provenance, quality,
and power. Coverage was 100% on both streams. Twenty-two stage outcomes were
`complete`; eight control/summary/presentation outcomes were honestly
`no_result`. The system did not claim a detection: both stream summaries carry
`scientific_confidence=rejected`. One stream nevertheless had candidate-only
QAM accuracy 0.9258 and a fitted slope around -2264.8 Hz/s, demonstrating why
candidate metrics are kept distinct from a qualified scientific conclusion.

The sequential worker took about seven minutes and remained near 300 MiB RSS
at the observed high-water point. Standard analysis is therefore currently
slower than a 60-second capture with one worker. Multiple lower-priority
workers, algorithm profiling, and post-RAID-resync measurements are required
before claiming sustained 100% capture-plus-analysis duty.
