# Three distinct raw adaptive scans through ARM

## Completed physical mixed-recording results

All three distinct recordings completed on PLUTO+ **192.168.1.15**, using local
IQ and a bounded queue of 48 dwells: **6,649/6,649 dwells, zero failures or
rejections, 48,647 passing GLRT candidates**. This completes the requested
recorded-data experiment, but **does not pass real-time qualification or full
native-chain positioning reproducibility**.

| Result | f363 (lower) | b34e (lower) | ee28 (upper) |
|---|---:|---:|---:|
| Completed dwells | 2,215 | 2,218 | 2,216 |
| ARM passing GLRT candidates | 16,191 | 18,397 | 14,059 |
| Standard-server passing candidates | 10,066 | 12,095 | 8,563 |
| Server candidates matched under frozen tolerances | 8,245 (81.9%) | 9,562 (79.1%) | 6,870 (80.2%) |
| Eligible server segments represented | 55/62 | 58/64 | 53/62 |
| One-to-one track matches | 45 | 46 | 41 |
| ARM track hypotheses / unmatched outputs | 80 / 35 | 86 / 40 | 75 / 34 |
| Short segments represented | 7/9 | 5/5 | 12/14 |
| Medium segments represented | 23/25 | 20/22 | 22/29 |
| Long segments represented | 25/28 | 33/37 | 19/19 |
| Peak queued dwells | 2 | 40 | 17 |
| Maximum dwell latency (seconds) | 0.337 | **5.479** | 2.394 |
| Downstream controller wall time (seconds) | **304.410** | **310.180** | 233.975 (unloaded drain) |

The first two downstream intervals exceed the unchanged 300-second limit;
maximum dwell latency exceeds the unchanged five-second limit. The final scan
waits 14.546 seconds for downstream capacity. Sampled aggregate peak RSS is
299,516 KiB (292.5 MiB); five-second sampling can miss peaks and double-count
shared pages. Maximum live IQ buffers are 41 of the bounded 50-buffer pool.
The last downstream interval is an unloaded drain, not loaded-throughput proof.
Represented segments total 166/188 (88.3%); this is agreement with server
segmentation, not physical detection recall. Unmatched tracks are not proven
false positives. The agreed reference #10 exception applies only to f363.

### Measured ARM stage times

Seconds; the first two downstream chains overlap the next detector. Summed
per-call wall times differ from CPU time and from paced process lifetime.

| Stage | f363 | b34e | ee28 |
|---|---:|---:|---:|
| GLRT: sum of active call wall times | 260.701 | 292.530 | 284.625 |
| GLRT: sum of active call CPU times | 261.494 | 286.228 | 276.809 |
| Observation/support projection: summed wall | 7.531 | 8.768 | 6.901 |
| Seed generation | 3.914 | 4.408 | 2.832 |
| Tracking | 4.181 | 5.361 | 3.583 |
| Conversion and exclusive membership selection | 2.661 | 2.938 | 1.942 |
| Orbit generation | 5.660 | 5.483 | 5.151 |
| Regional search: 400 points | 282.332 | 289.210 | 218.393 |
| Selected-point associations | 4.619 | 2.454 | 1.804 |
| Other positioning process overhead | 0.993 | 0.265 | 0.226 |

IQ file I/O totals 96.072 / 100.360 / 100.303 seconds, overlapping the worker;
do not add these to GLRT times. Detector process wall times include five seconds
of initial lead and paced waiting. End-to-end elapsed time from first replay
origin to final downstream completion is 1,149.021 seconds.

### Stage comparison verdicts

- **Raw IQ:** every full dwell hash/event agrees with independent server decompression.
- **Native-control GLRT:** CFOs, epochs, ranks, completion and passing decisions
  agree exactly for all three scans; score differences are at most 5.56e-16.
  Standard-server fractional GLRT is a different algorithm; its matching counts
  above use the predeclared source/RX, two-sample epoch and 10 kHz CFO tolerances.
- **Identical-checkpoint module controls:** observations, support, seeds and tracks
  match byte-for-byte. All 400 search coordinates and selected coordinates agree;
  search score differences are at most 6.03e-11 Hz. Association satellite/time-offset
  choices agree exactly; numeric differences are below 7.4e-10 Hz, within the
  existing 1e-9 Hz tolerance. Association JSON is not byte-identical on the last
  two captures. The original strict failures in `qualification-summary.json`
  remain preserved; `native-association-roundoff.json` supplies the numerical audit.
- **Server orbit/association controls:** physical ARM propagated positions differ
  by at most 1.93e-10 km per component. With identical published memberships,
  satellite/time-offset choices agree for 59/59, 55/55 and 63/63 tracks at each
  of two reference sites. Maximum individual held-out residual difference is
  0.117 Hz. These are evaluation controls, not runtime server inputs.
- **Independent raw-IQ native chain:** memberships agree, but rounding-sensitive
  track identities change held-out partitions and positioning scores. In ee28,
  the selected grid offsets change from ARM (-75, -75) to host (-81.25, -81.25).
  This is a material reproducibility failure, isolated below.
- **Positioning versus published server results:** ARM selected regional offsets
  are (-75, -75), (-81.25, -81.25), (-75, -75); published server offsets are
  (-81.25, -68.75), (-81.25, -81.25), (-75, -75). All ARM searches exhaust the
  400-point budget with `complete:false`. Agreement of selected offsets does
  not establish convergence or a validated position fix. Server GLRT/tracking
  controls are fresh; server final positions are existing published references.

Next implementation work is a versioned membership-based identity/partition
policy that excludes derived floating summaries, followed by reducing loaded
search cost and detector backlog. Published v1 identities remain unchanged.
Live RF acquisition and Pi/RTL-SDR remain unqualified.

Plots: [cadence and latency](arm-cadence.png), [stage timings](stage-timing.png),
and each session's `comparison/glrt-cfo.png` and `comparison/tracks.png`.
Track plots show assigned points rather than fitted straight lines. Evidence:
`arm-sequence-v2/`, `stage-comparison.json`, `qualification-summary.json`,
`native-association-roundoff.json`, and the per-session comparison receipts.
The final component-owned bench regression run passes **148 tests in 32.79 s**
(`final-bench-tests.log`). Current harness, queue wrapper and test sources are
hashed in `qualification-sources-final/sha256.json`; earlier execution snapshots
are preserved separately.

## Initial failed trial and capacity-only retry

`arm-sequence-v1/` fails lossless and real-time acceptance: the second capture
rejects visits 835, 849 and 882 when its 32-dwell queue fills. Those visits
contain 25 passing native GLRT candidates. Every processed visit retains exact
CFOs and passing decisions versus the native host control; maximum score
difference is 5.55e-16. The first downstream chain takes 303.446 seconds, exceeding
the 300-second limit. The controller stops explicitly and preserves partial
products; this is not a successful three-scan run.

Measured-service FIFO estimates suggest a no-loss peak of 35–36 queued dwells
and 4.80–4.91 seconds maximum latency. Those estimates are not hardware results.
`arm-sequence-v2/` is a capacity-only retry with 48 queued dwells and at most 50
IQ buffers (120,000,000 bytes). Detector/scientific code and scheduling are
unchanged. The 300-second downstream and five-second latency acceptance limits
remain unchanged. All 21 recorded-queue tests pass, including absorbed bursts
and explicit overload rejection at both capacities. The retry completed with
the results above; increased capacity removed loss but did not meet latency.

Requested scope: finish bounded-queue qualification, then process three distinct
existing DS9 recordings in sequence on ARM and compare every stage with server
results. `selection.json` freezes the final three chronological 2.5 MS/s DS9
captures: `f363c7f29141d0b1`, `b34e380766e24b3b`, `ee2831131a88440f` (all IDs have
the `scan-fw-` prefix). They contain 2,215, 2,218 and 2,216 dual-receiver dwells.
All three capture digests and completed published position references were
verified through the read-only maintained-server interfaces.

The captures have distinct original UTC epochs. Replay must preserve those
epochs, receiver/retune metadata, IQ bytes and capture-specific TLE authority.
Sequential execution does not make the gaps between recordings continuous RF.
No new RF collection is involved. Host staging and oracle generation may run
while the separate queue test executes; no new data is staged onto PLUTO during
that timing trial.

The preceding four-repeat queue-32 qualification passed all declared gates:
8,860 dwells, no loss, 64,764 observations, three loaded downstream intervals
297.086–297.852 seconds, maximum dwell latency 2.913 seconds. This does not
predetermine the result for three different recordings.

`raw-iq-comparison.json` independently verifies all 6,649 full exported dwell
hashes and events against fresh server decompression. Each device export is
also verified in full before the measured replay. `tests.log` records 156
passing tests; subsequent comparison and serialization regression tests are
recorded separately. `evaluator-smoke/` exercises comparisons against the prior
completed baseline run and is explicitly not a new hardware run.

## Reproducibility issue exposed by the independent full chain

`native-host-pipeline-v2/` in each session starts from fresh raw-IQ native GLRT
and independently completes every subsequent module. Its baseline candidate
CFOs and track memberships match the prior ARM run. However, tiny rounding
differences in track fit summaries change the private track identity and hence
the downstream training/held-out partition. That changes positioning scores
even with identical memberships. The controlled diagnosis in
[`roundoff-identity-diagnosis/`](roundoff-identity-diagnosis/README.md) isolates
the cause without altering original results. The timed ARM trial retains the
frozen implementation. Same-checkpoint module parity and independent full-chain
parity must be reported separately.

Before starting the ARM experiment, the diagnostic downstream timeout was
increased to 600 seconds to permit a slow recording to finish for scientific
comparison. The acceptance limit remains **300 seconds**. Host controls show
substantial recording-to-recording cost variation. `orchestration-adjustment.json`
records that only the host staging coordinator was replaced; the already-active
IQ transfer/verification child continued, and no ARM experiment had started.

| Boundary | Comparison |
|---|---|
| Raw IQ and timing | Every visit's bytes/hash, full event, rate, receiver layout and original sample-counter/UTC mapping agree. |
| GLRT | ARM versus same-algorithm native host control; separately compare against fresh standard-server fractional GLRT by source/RX, CFO/epoch agreement, scores and passing counts. Different algorithms are not required to produce identical ranks or counts. |
| Observations/support | Exact native host/ARM checkpoints and identities; separately compare membership of server detections under declared matching tolerances. |
| Tracks | Exact native host/ARM memberships; server segment representation, one-to-one matches, short/medium/long recovery and unmatched outputs. Reference #10's historical exception applies only to the original baseline scan. |
| Orbits and associations | Same capture epoch/TLE catalogue for native host/ARM; compare propagated states, satellite/time-offset choices and residuals with server controls. Published memberships remain evaluation-only. |
| Positioning | Full native search trace, selected grid point, final associations, completeness and resource use; report differences from the published server position and membership/model differences explicitly. |

Fresh server controls use the frozen clean maintained-server checkout and public
detector, with explicit session/digest/count arguments carried into each worker.
The generalized evaluation harness is derived from the prior full-scan oracle;
its original remains unchanged. Seven scope/worker-authority tests pass. A
two-visit smoke run for the new `b34e` capture passes and is explicitly marked
incomplete, preventing it from being mistaken for full coverage.

`server-processes.json` records three bounded (900-second) server jobs, each with
one worker and BLAS/OpenMP thread limits of one. These run only on the host.
All three full server detector jobs completed within their bounds. Fresh server
tracking produced 63, 64 and 62 tracks respectively, from 10,066, 12,095 and
8,563 passing fractional GLRT candidates. Independent scalar native host GLRT
controls also completed (16,191, 18,397 and 14,059 passing candidates). These
are different detector algorithms; candidate-count ratios are not recall.
ARM staging/execution and final comparisons are complete. Successful process
completion does not override the failed qualification gates reported above.

Per-scan `prepared/manifest.tsv` and `prepared/authority.tsv` now cover all
6,649 dwells. The first two captures use lower-edge templates; the third uses
upper-edge templates. The builder retains each capture's qualified UTC bracket
width and acquisition generation, uses integer counter differences for arrival
offsets, and rejects overlapping visits, wrong rates, changed identities and
invalid lanes. Sixteen preparation/scope tests pass (`preparation-tests.log`).
These manifests are plans only: raw file presence and hashes must be independently
verified before hardware execution. The immutable detector analysis identity
comes from the qualified GLRT configuration; wrapper binaries and execution
settings are pinned separately.
