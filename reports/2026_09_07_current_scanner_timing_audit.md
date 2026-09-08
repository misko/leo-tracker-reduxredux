# Current production scanner: dwell, hop, duty, and analysis timing

Read-only production audit, 2026-09-07, approximately 22:27-22:35 UTC.
No services, radio configuration, firmware, or production code were changed.
The deferred FPGA work is saved separately in
[the future PSS timing plan](../docs/architecture/future-fpga-pss-timing-plan.md).

## Summary

The current persistent-hop scanner retains **120 ms of valid dual-receiver
IQ per channel edge**, takes approximately **125.6-125.8 ms between visit
starts**, and revisits each edge approximately once per second. Its latest
completed native-rate pair retained **286.8 s and 286.2 s** of valid IQ within
approximately 300 s of device time: **95.56% and 95.39% valid-IQ duty**.
Each individual edge receives about 35.8 s, spread across 298-299 visits.

This is the existing IQ scanner, not the experimental FPGA PSS-only tracker.
The automatic fractional-GLRT pass currently analyzes one 20 ms probe per
120 ms visit per receiver. Recording coverage and analyzed temporal coverage
must not be conflated.

## Evidence and deployed identity

- Both `/opt/leo-tracker/current-acquisition` and `/opt/leo-tracker/current`
  selected release `39146ee83d00523fbd37ba02179c87a5c241a017`.
- `leo-acquisition.service` was active; its running PID was 3852299.
- Effective settings were read from that process's environment, not inferred
  from an old checkout or one environment file. `/etc/leo/acquisition.env`
  overrides the base file's `LEO_SCANNER_ENABLED=false` with `true`.
- The active scanner radio is `radio_pluto_5d4d`, serial
  `1040005e0b100007100010000bf33a5d4d`, URI `ip:192.168.1.20:30432`.
- The release-local alternate iiOD provenance pins libiio
  `c752ab684a4c9924ee362ccfb02a7ac65f7992f9`, with the userspace hop provider,
  not the experimental kernel persistent-hop provider. That clean local
  checkout was inspected to interpret the event timestamps.
- Primary measurement sources are the following two published manifests:
  - `/srv/bulk/leo/scanner-hop-recordings/2026/09/07/scan-hop-0cff88ddaeec79f2/manifest.json`,
    SHA-256 `e511d9faa23877b8390b5cca0e9856170b700263f4c7da7c4930e71bafb9811c`;
  - `/srv/bulk/leo/scanner-hop-recordings/2026/09/07/scan-hop-6762d7b8fced3bfc/manifest.json`,
    SHA-256 `2f7532725af2eaa2017d31f0a3fa24f93c318adf15062f8a264f77cfcbbaefba`.
- History/analysis status was checked through
  `GET /api/v3/scanner/persistent-sessions`. The V2 endpoint reports the older
  V1 analysis product; its pending status does not mean fractional V2 analysis
  is missing. The capture record's initial `pending_backpressure` text is also
  not the current fractional-analysis status.

All timing statistics below were recomputed from metadata. IQ payloads were
not reread or independently rehashed in this audit. Continuity and restoration
statements describe the published, qualified receipts.

## Scheduling and RF geometry

| Setting | Effective production value |
| --- | --- |
| Scanner enabled | Yes |
| Capture mode | Persistent hop |
| Scheduled start interval | 1,200 s / 20 minutes, UTC-slot aligned |
| Nominal device observation span | 300 s |
| Maximum start lateness | 300 s; later queued slots are skipped |
| Rate policy | Alternating complete runs: 2.5, 5, 2.5, 5 MS/s |
| RF bandwidth | 2.5 MHz or 5 MHz, matching the run's sample rate |
| Valid dwell per target | 120 ms |
| Receivers | RX0 and RX1 simultaneously, same tuned edge |
| Gain | Manual, 40 dB |
| Post-transition invalid guard | 1,000 us / 1 ms |
| DMA block | 131,072 samples; 8 kernel buffers |
| Host read-ahead | 8 visits |
| Storage queue | 64 visits |

The sample rate remains fixed throughout a run. The 50/50 policy is by
alternating scheduled runs, not 150 s at each rate inside one run and not an
alternating rate at every hop. Failed/skipped slots can unbalance the retained
dataset even when the schedule remains balanced.

The exact sequence repeats:

`CH1L -> CH2L -> CH3L -> CH4L -> CH1U -> CH2U -> CH3U -> CH4U -> CH1L`.

| Target | RF center (MHz) | Receiver IF center (MHz) |
| --- | ---: | ---: |
| CH1L | 10709.6875 | 959.6875 |
| CH2L | 10959.6875 | 1209.6875 |
| CH3L | 11209.6875 | 1459.6875 |
| CH4L | 11459.6875 | 1709.6875 |
| CH1U | 10940.3125 | 1190.3125 |
| CH2U | 11190.3125 | 1440.3125 |
| CH3U | 11440.3125 | 1690.3125 |
| CH4U | 11690.3125 | 1940.3125 |

These centers apply at both currently scheduled rates. The canonical function
chooses the pilot-nearest center whose nominal bandwidth fits inside the
occupied channel, using the documented 9.75 GHz LNB LO. Both 2.5 and 5 MHz fit
without shifting away from these centers. This is configured digital/RF
geometry, not a new measurement of the analog passband or LNB calibration.

The same supervisor also queues ordinary 60 s fixed-channel recordings on a
180 s cadence, presently using a mixed 2.5/25 MS/s policy. That is a separate
mode; 25 MS/s is not the scanner's current high-rate slot. Radio ownership and
the durable acquisition queue serialize operations. Actual scanner starts can
therefore be later than the scheduled UTC tick.

## Execution path

1. Persist a rate-resolved scanner intent for the UTC slot and acquire radio
   ownership. Check storage admission and whether this intent is already
   durably published.
2. Enter/attest the release-local alternate iiOD lifecycle on port 30432.
   Configure the rate, bandwidth and gain and prepare eight Fast Lock profiles.
3. Keep one physical-LAN IIO context and continuous receive stream active.
   A radio-local userspace thread schedules hops using the device sample
   counter. The host does not open/close a receive buffer for every target.
4. For each visit, bracket the radio control transition with device counters,
   discard the complete transition plus the 1 ms guard, and retain exactly
   300,000 samples at 2.5 MS/s or 600,000 samples at 5 MS/s per receiver.
5. Receive metadata-attested blocks continuously, reassemble valid visits,
   and compress/write asynchronously. Transition samples are absent from the
   retained IQ but their intervals remain explicit in the receipt.
6. Finish a complete visit when the nominal 300 s span is reached, obtain the
   terminal/continuity receipt, restore radio state, clean up alternate iiOD,
   and publish the immutable bundle. Small endpoint overshoot is expected.
7. A separate low-priority worker analyzes the published IQ and renders plots.

The plan's 2,500 visits is a maximum, not an expected achieved count. It is
300 s divided by 120 ms with zero overhead. Real transitions reduce the count
to approximately 2,390 within the time budget.

## Measured per-hop breakdown

The following means exclude the initial startup transition. They describe
2,389 transitions at 2.5 MS/s and 2,384 at 5 MS/s.

| Stage | 2.5 MS/s mean | 5 MS/s mean |
| --- | ---: | ---: |
| Valid samples on the preceding edge | 120.000 ms | 120.000 ms |
| Valid-end to control-transition start | 0.389 ms | 0.469 ms |
| Counter-bracketed control transition | 4.181 ms | 4.328 ms |
| Explicit guard after transition | 1.000 ms | 1.000 ms |
| Total invalid interval | 5.570 ms | 5.796 ms |
| Start-to-start interval | 125.570 ms | 125.796 ms |

The control bracket is not a measurement of PLL settling alone. The exact
`userspace_recall` path includes release of the tandem gain-control session,
Fast Lock recall, active-profile verification, tandem reacquisition, and
counter access. The saved counters do not divide that 4.2-4.3 ms into finer
substeps. The preceding 0.4-0.5 ms includes scheduler wakeup/counter/lock-path
latency; it is not an additional configured dwell or guard.

| Distribution | 2.5 MS/s | 5 MS/s |
| --- | ---: | ---: |
| Invalid interval median | 4.724 ms | 5.917 ms |
| Invalid interval p95 | 7.875 ms | 6.828 ms |
| Invalid interval p99 | 11.954 ms | 9.257 ms |
| Invalid interval maximum | 18.793 ms | 13.233 ms |
| Same-edge revisit mean | 1004.569 ms | 1006.370 ms |
| Same-edge revisit p95 | 1009.595 ms | 1011.667 ms |
| Same-channel lower-to-upper mean | 502.248 ms | 503.241 ms |

The largest remaining hop overhead is the radio control bracket, approximately
75% of invalid time. The explicit 1 ms guard contributes about 17-18% of
invalid time. These are observations, not authorization to reduce the guard
or modify the control path.

## What the 300 seconds contain

| Quantity | 2.5 MS/s scan | 5 MS/s scan |
| --- | ---: | ---: |
| Session ID suffix | `0cff88ddaeec79f2` | `6762d7b8fced3bfc` |
| Manifest creation, UTC | 22:00:04.033 | 22:20:04.335 |
| Device-counter span | 300.111054 s | 300.025274 s |
| Retained valid IQ time | 286.800 s | 286.200 s |
| Startup/transition invalid time | 13.311054 s | 13.825274 s |
| Valid-IQ duty | 95.5646% | 95.3920% |
| Visits | 2,390 | 2,385 |
| Full eight-edge sweeps plus tail | 298 + 6 visits | 298 + 1 visit |
| Retained time per individual edge | 35.76-35.88 s | 35.76-35.88 s |
| Recorded missing samples / overflows | 0 / 0 | 0 / 0 |
| Manifest creation to finalization | 304.354474 s | 304.081038 s |
| Uncompressed dual-RX IQ | 5.736 GB | 11.448 GB |
| Compressed IQ | 1.910 GB | 4.295 GB |

The counter span is the appropriate denominator for the reported scan duty.
The host bundle lifecycle additionally includes setup, transfer drain,
restoration, compression finalization, and durable publication. It begins
after outer admission/lifecycle work, so it is not a complete measurement of
the scanner's radio lease duration.

Within that measured host lifecycle:

- creation to estimated first device sample: 1.107 / 1.053 s;
- estimated first sample to host terminal receipt: 301.077 / 300.982 s;
- terminal receipt to bundle finalization: 2.170 / 2.045 s.

These broad timestamps cannot isolate network drain, settings restoration,
and fsync individually. The first-sample UTC mapping is host-bracketed to
about 1.13 / 1.24 ms, whereas relative visit boundaries use device counters.

At a 20-minute cadence there are three different useful duty definitions:

- any scanned edge during a scan: approximately **95.5%**;
- one particular edge during a scan: approximately **11.9%**;
- any scanned edge over the full 20-minute schedule: approximately **23.9%**,
  assuming a successful slot; one particular edge is approximately **3.0%**.

RX0 and RX1 are simultaneous observations of the same tuned edge. They improve
available receiver evidence but do not double unique wall-clock coverage.
The same edge is absent for approximately 0.885 s between 120 ms visits.
Upper and lower of the same channel are observed approximately half a second
apart, not simultaneously; trajectory joins must respect that time separation.

## Buffers and storage are not extra per-hop waits

131,072 samples represent 52.429 ms at 2.5 MS/s or 26.214 ms at 5 MS/s.
Eight kernel buffers represent approximately 419 / 210 ms of stream capacity.
Visits can cross block boundaries. The continuous stream and sample-counter
metadata let the client recover exact 120 ms visits without equating a block
refill with a channel dwell or discarding an entire buffer at every hop.

The writer queue reached only 3/64 and 5/64 visits in these two scans, with zero
enqueue failures. Maximum enqueue wait was 0.191 / 0.042 ms. Individual writer
service maxima were 402 / 714 ms, but that work runs asynchronously and cannot
be added to every hop. The observed queue headroom does not support calling
disk writing the dominant bottleneck in these two successful captures.

## Current automatic analysis cadence

The installed worker command uses two workers, one session per invocation,
and `--probe-stride-ms 120`. Its product is
`persistent-hop-fractional-glrt64-cfo-v2`, with fractional scores required for
decisions and `circular-five-cell-log-parabola-plus-lanczos16-v1` refinement.

The detector receives a 20 ms slice at each configured probe start. With a
120 ms visit and 120 ms stride, this is the **first 20 ms only, once per
receiver per visit**: 4,780 and 4,770 probes for these sessions. Up to eight
acquisition candidates are considered per probe. All 120 ms of IQ remains
stored and available for a denser replay; it is not discarded by this analysis
sampling policy. The first-pass non-overlapping sampled time is approximately
47.8 / 47.7 s across the scan per receiver, or 15.9% of the device span, and
about 6 s per edge. This is an input-window accounting metric, not a claim
that every sample or probe provides an independent valid Doppler estimate.

The worker timer runs roughly one minute after the preceding invocation ends,
not once per hop. In the observed examples:

- 22:00 2.5 MS/s scan: finalized 22:05:08; analysis began 22:05:44 and completed
  22:10:52, about 5 min 44 s after capture publication;
- 21:40 5 MS/s scan: finalized 21:45:08; analysis began 21:45:33 and completed
  21:53:51, about 8 min 43 s after publication;
- latest 22:20 5 MS/s scan: analysis completed at 22:33:00, about 7 min 52 s
  after publication.

These are observed turnaround times, not SLAs. Analysis runs after capture,
so its several-minute runtime is not dead time between RF hops. Device-counter
coordinates, including the discarded transition gaps, remain necessary for
GLRT/CFO time axes; concatenated valid-only IQ must not be treated as one
gapless wall-clock recording.

## Health caveats and boundaries

The latest two captures were complete, qualified, continuity-attested, and
restored according to their receipts; their fractional analyses completed.
Earlier journal entries at 21:20 and 21:22 recorded failures because received
IQ blocks did not cover an attested visit, followed by terminal-recovery
errors. A 20:40 capture was unqualified and shorter than 300 s. Therefore
95.5% is measured duty for successful recent scans, not a blanket assertion
that every scheduled slot succeeds. No failure remediation was attempted.

The ordinary fixed-channel 25 MS/s recording path also logged gaps. It is
separate from these qualified 2.5/5 MS/s hopping receipts and should not be
used to infer missing IQ in them.

## Reproduction of the stage accounting

For each visit after startup, let `s` and `e` be its invalid interval's start
and exclusive end, `b` and `a` the transition-before/after counters, and `f`
the configured sample rate. The audit computes:

- pre-control interval: `(b - s) / f`;
- control bracket: `(a - b) / f`;
- guard: `(e - a) / f`;
- complete invalid interval: `(e - s) / f`;
- valid time: `valid_sample_count / f`;
- same-edge revisit: difference between valid-start counters eight visits
  apart, divided by `f`;
- run duty: sum of retained valid samples divided by the receipt's full
  device-counter span, without multiplying by the number of receivers.

Production source anchors at release `39146ee8`:

- `src/leo/cli/composition.py`: effective settings, plan compilation,
  alternate iiOD lifecycle, capture publication;
- `src/leo/cli/runner.py`: UTC cadence, durable intent queue, lateness gate,
  deferred analysis;
- `src/leo/scanner/schedule.py`: alternating whole-run sample rates;
- `src/leo/scanner/persistent_hop.py`: 300 s / 120 ms plan and receipt contracts;
- `src/leo/contracts/starlink_frequency.py`: channel/IF/bandwidth geometry;
- `src/leo/radio/pluto_persistent_hop.py`: one context, producer/read-ahead,
  visit assembly and terminal evidence;
- `src/leo/scanner/detector.py`: 20 ms probe slicing;
- `src/leo/cli/persistent_hop_analysis.py`: fractional analysis and worker policy;
- libiio `c752ab6`, `iiod/spf-hop-scheduler.c` and
  `iiod/spf-hop-device-userspace.c`: sample-counter deadlines and the measured
  transition bracket's actual operations.
