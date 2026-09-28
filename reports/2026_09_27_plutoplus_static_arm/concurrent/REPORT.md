# Simultaneous adaptive capture and single-core GLRT on PLUTO+

Latest: [40% headroom optimization](../optimize/GOAL40.md) achieves
42.7–44.1% CPU0 headroom in two recorded-cadence capture runs. The original
baseline and earlier follow-up below predate that selected build.

Date: 2026-09-27. Target: 192.168.1.15, serial
104000b29905000e17000800065934759d, Cortex-A9, firmware v0.54.

Later results: [exact ARM kernel optimization and concurrent qualification](../optimize/REPORT.md)
reduce dual-RX capture-overlap CPU time to 103.33 ms with IRQ on CPU1.
The original measurements below remain the baseline comparison.

**The current adaptive cadence can accommodate dual-RX GLRT on average in
these short contention tests, but continuous 120-ms arrivals overload it.**
The most useful configuration is GLRT on CPU0, with IIO and the Ethernet
interrupt on CPU1. Single-RX online GLRT offers substantially more headroom.
Continuous raw dual-RX recording to the attached SD card does not keep up.

The GLRT itself remains single-threaded and uses one core. Capture and system
work use the other core too; this is not qualification of the entire pipeline
on one total CPU core.

## What was measured

Seven 45-second receive-only adaptive scans were performed following the
user's request to benchmark simultaneous capture. Total authorized acquisition
time was 315 seconds. All **2,309 planned visits were delivered**, with zero
skips, invalid visits, cancellations or host classifier drops. Every campaign
returned an exact receiver-settings/kernel-buffer restoration receipt with
Fast Lock inactive. No firmware was installed and no production service was
stopped. Ethernet IRQ affinity was changed temporarily for two experiments and
restored to its original CPU0 mask after each.

Radio capture: native 2.5 MS/s, both receivers, four lower-edge frequencies,
fixed 120-ms dwell, 20-ms transition budget, host energy feedback every eight
visits. The existing IIO read/write worker affinity was already CPU1. The
fixed-dwell protocol-1 API was used because this firmware does not support
the current variable-dwell protocol-3 runner. Live 5/7.5-MS/s adaptive capture
is not supported by its advertised capabilities; the earlier static GLRT
four-rate support remains separate.

GLRT: a persistent optimized D worker, eight fixed real development inputs
(first four visits from each of two previously selected sessions), both
receivers serially unless explicitly labeled single RX. Inputs are resident
saved IQ, scientific kernels/flags are unchanged, and every result is compared
with its original D receipt. **6,900/6,900 receiver-result comparisons match
exactly after removing timings.** Repeated visits are not independent science
fixtures. Nineteen component tests pass.

This is actual live-capture contention plus saved-IQ GLRT, not a completed
integration that analyzes each newly captured visit or uses GLRT to drive live
feedback. Live IQ was streamed to an uncompressed host archive under
/var/tmp/leo-arm15-concurrent-iq; this differs from production per-visit
compression/fsync. Capture bytes, records, hashes and restoration receipts are
retained. There was no radio transmission.

## CPU budget

CPU figures below exclude iowait from executing CPU, and include kernel and
softirq execution. They use complete one-second intervals within the common
capture/GLRT measurement window, not the idle portions of the session.

| Workload | CPU0 busy | CPU1 busy |
|---|---:|---:|
| Idle | 0.2% | 0.6% |
| Capture only | 15.2% | 23.9% |
| GLRT only, dual RX every 120 ms | 89.6% | 0.7% |
| Capture + dual-RX GLRT every 120 ms, original IRQ placement | 99.9% | 32.3% |
| Same, Ethernet IRQ on CPU1 | 99.9% | 42.6% |
| Capture + GLRT at recorded arrivals, original IRQ placement | 98.0% | 31.6% |
| Same, Ethernet IRQ on CPU1 | 90.1% | 42.7% |
| Capture + single-RX GLRT every 120 ms | 64.0% | 27.8% |

Capture alone uses nearly 12% of CPU0 in softirq work, despite IIO workers
being assigned to CPU1. Moving Ethernet IRQ 35 to CPU1 changes that placement
and reduces GLRT interference. Shared-memory contention remains; IRQ placement
does not eliminate capture's cost.

## Continuous 120-ms stress and alternatives

Times here are from GLRT jobs completely inside the live capture window.
Response includes queue delay and JSON publication; compute CPU does not.
Deadline counts use each job's configured period, including the 140-ms row.

| Configuration | Jobs in overlap | Mean GLRT CPU ms | Mean response ms | p95 response ms | Deadline misses |
|---|---:|---:|---:|---:|---:|
| Dual RX, 120 ms, original IRQ | 337 | 129.94 | 2,905.71 | 4,770.14 | 337/337 |
| Dual RX, 120 ms, IRQ on CPU1 | 371 | 118.33 | 330.93 | 398.50 | 371/371 |
| Dual RX, 140 ms, original IRQ | 319 | 130.08 | 165.87 | 348.52 | 201/319 |
| Single RX, 120 ms, original IRQ | 373 | 63.86 | 67.74 | 107.85 | 3/373 |

Without capture, dual-RX GLRT averaged 109.56 ms CPU, with zero publication
deadline misses across 500 calls. A final 120-call baseline after all tests
averaged 109.72 ms CPU and also had zero misses.

At original affinity and 120-ms pacing, queue delay grew to 4.86 seconds over
the full run. Moving the IRQ reduced maximum queue delay to about 0.34 seconds,
but left the GLRT core saturated. Single-RX processing recovered quickly from
brief delays (maximum queue 43.6 ms), but still had three late results and
does not provide online evidence for the unprocessed receiver.

The 140-ms run deliberately changes input pacing. It cannot be called a
same-coverage speedup or proof that live arrivals satisfy a 140-ms deadline.

## Actual adaptive arrival pattern

The first live scan delivered 330 visits in approximately 45 seconds. Mean
host delivery spacing was **136.16 ms**, but individual gaps ranged from
**22.58 to 371.62 ms** (median 30.41 ms; p95 342.67 ms).
Capture/transport therefore presents bursts rather than
an evenly spaced sequence. We replayed these exact relative arrival offsets
against the fixed saved-IQ cases during another live capture, once per IRQ
configuration. This tests that recorded scheduling workload; it is not a
closed-loop test of the new capture's own arrival times.

Both 330-job runs completed without a sustained rising queue over this short
recorded schedule. The first/last 50 jobs' mean queue delays were 107.49/112.20
ms at original affinity and 101.54/94.41 ms with IRQ on CPU1. Final queue delay
returned near zero in the original-affinity run; both finished soon after the
last scheduled input. Short runs cannot establish long-term queue stability.

| Recorded-arrival configuration | Overlap mean GLRT CPU ms | Overlap p95 published response ms | CPU0 busy |
|---|---:|---:|---:|
| Original IRQ placement | 130.36 | 353.53 | 98.0% |
| Ethernet IRQ on CPU1 | 119.69 | 309.98 | 90.1% |

Thus keeping up on average with today's scan cadence is more achievable than
finishing every result within 120 ms. Burst buffering is necessary. These
latencies begin at saved-input release, not at RF observation start, and do not
include GLRT feedback application. The host energy classifier supplied the
live scan's feedback throughout these tests.

## Attached SD card

A separate no-RF experiment ran GLRT on CPU0 while a CPU1 writer attempted
2.4 MB every 120 ms, the **20 MB/s** required by dual-RX CI16 at 2.5 MS/s.
It wrote 500 blocks (1.2 GB) to a new file, followed by fdatasync.

- Completion took **98.94 seconds**, equivalent to **12.13 MB/s** including
  final sync; the final sync itself took 46.15 ms.
- Writer queue delay reached **36.75 seconds**. Page caching did not hide the
  sustained shortfall once the workload exceeded available cache.
- Concurrent GLRT also suffered: 492/500 published results exceeded 120 ms.
- The target reports a **33.33 MHz, four-bit SD bus**, giving a theoretical
  signaling ceiling of about **16.67 MB/s** before protocol overhead—already
  below the requested 20 MB/s payload.

The 238-GiB capacity is useful for development fixtures and selected recordings,
but does not imply enough write bandwidth. Reformatting alone cannot fix the
observed bus ceiling. This test evaluates filesystem writing plus GLRT; it does
not qualify a native capture-to-SD implementation. Raw single-RX recording
would require 10 MB/s, but that combined pipeline has not been benchmarked.

## Ranked options

1. **Keep dual-RX capture/GLRT, isolate networking on CPU1, and use a persistent
   worker with a bounded queue.** This best preserves the intended evidence.
   Recorded-cadence replay fits on average, but only about 10% of CPU0 remains
   free. Require additional optimization and an integrated live-input/feedback
   test before deployment. Do not advertise a strict 120-ms deadline.
2. **Use one receiver for continuous online GLRT and retain both IQ streams.**
   Measured compute drops to about 64 ms during capture, leaving much more
   headroom. Analyze the second receiver selectively or later. Selection and
   second-RX confirmation are new policies requiring science evaluation;
   full dual-RX online evidence is lost when that receiver is not analyzed.
3. **Reduce repeated acquisition work while preserving fresh confirmation.**
   Combine IRQ isolation with the earlier ranking/acquisition optimization or
   causal tracking experiments. Target 80–90 ms of combined-load compute per
   dual-RX visit, then measure tails and reacquisition. This speed is a target,
   not a result measured here.
4. **Relax scan cadence or evidence latency explicitly.** A slower average
   cadence can fit the current detector, but bursts still need buffering;
   changing dwell/revisit policies changes observation coverage. A later idle
   period between recordings does not rescue real-time adaptive feedback.
5. **Keep full-rate IQ off the SD card in its current configuration.** Network
   streaming worked for all live test visits. Use SD for fixtures, selected IQ
   or reduced-volume records; qualify any bus/driver or encoding change
   separately before relying on sustained local archival.

## Reproduction and limitations

The runnable components are paced.c (paced_v1.c binds the original paced-arm
binary), monitor.c, capture.py, run_phase.py, run_irq_phase.py, sd_writer.c and
summarize.py. Original scientific sources/flags remain in ../build-snapshot.tar.gz;
the paced build command is in paced-build.json. The arrival-offset file derives
only from scan-only/capture/visits.jsonl. Per-phase run.json records exact
commands and source/binary hashes; raw target receipts are retained locally
and beneath /mnt/glrtbench/leo-static-glrt.4jwvdm/concurrent-*.

Example host commands from the repository root (new phase names required):

```sh
.venv/bin/python reports/2026_09_27_plutoplus_static_arm/concurrent/run_phase.py new-glrt --core 0 --seconds 65
.venv/bin/python reports/2026_09_27_plutoplus_static_arm/concurrent/run_phase.py new-combined --capture --core 0 --seconds 75
.venv/bin/python reports/2026_09_27_plutoplus_static_arm/concurrent/run_phase.py new-arrivals --capture --core 0 --recorded-arrivals --jobs 330 --seconds 60
```

The latter two commands perform new bounded RF acquisition. Capture.py uses
the existing immutable host runtime and fixed .15 serial, restores settings
through the campaign API, and writes only new experiment paths. Existing
credentials are referenced, never embedded in receipts.

SOL reviewed the workload/restoration code and implemented the SD writer;
Terra implemented the CPU monitor and independently audited receipts. The
host-to-target clock mapping has approximately 0.1-second boundary uncertainty;
overlap edge job counts are approximate by a few jobs. One-second CPU counters
and these short repeated workloads do not establish hard real-time or thermal
guarantees. Scientific equality concerns the saved fixtures, not the newly
captured RF. Firmware, radio settings and Ethernet affinity are restored;
no optimized production pipeline was deployed.
