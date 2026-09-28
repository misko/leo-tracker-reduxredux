# Single-core PLUTO+ saved-IQ GLRT experiment

Status: design amended for implementation on 192.168.1.15. 2026-09-27.

## Four-rate development amendment (supersedes two-rate details below)

The user selected development host 192.168.1.15 and confirmed its SSH host key
changes every boot. Pin the current session key in an experiment-owned file.
This host reports Cortex-A9/NEON and two available processors; use CPU0 only.
The SD partition was visible (249,970,688 KiB) but unmounted and not recognized
by the available filesystem probes. The user subsequently authorized formatting:
it is now ext2, labeled GLRTBENCH, mounted at /mnt/glrtbench. Persist inputs,
executables and receipts in an experiment-owned directory there. Compilation
uses the existing host cross-toolchain; timed calls use resident mapped input.

Native input rates are 2.5, 5, 7.5 and 10 MS/s. The primary speed objective is
2.5 MS/s: >=1.30x is worthwhile and >=1.50x strong. Other rates require separate
correctness, memory and performance reporting; improvement at higher rates is
desirable but not a prerequisite for a useful 2.5-MS/s result. No downsampling
or lower-rate substitution is permitted. No rate may be described as supported
merely because its file loads; it must execute and pass the stated gates.

Keep the 64 real cases below and add all eight exposed development cases at
each of 7.5 and 10 MS/s from ../2026_09_26_ds5_server_eval/dataset/cases.json
(SHA-256 ce3a22f10abefca4623affe006331b770dad5d3788d99aa44bdad93d2f75af48).
Use all 24 controls, six per rate, from that manifest. Total: 80 real visits
and 24 controls, 104 physical cases. All added source files were hash-verified.

| Rate | Example real case | Samples/RX per 120 ms | Raw dual-RX bytes |
|---|---|---:|---:|
| 2.5 MS/s | seq-dev-r2500000-scan-fw-1a0e881391ba1d2f-v001678 | 300,000 | 2,400,000 |
| 5 MS/s | seq-dev-r5000000-scan-fw-3ec1c634e1f48f77-v000446 | 600,000 | 4,800,000 |
| 7.5 MS/s | real-dev-r7500000-scan-fw-247bd59bd5950cb1-v001452 | 900,000 | 7,200,000 |
| 10 MS/s | real-dev-r10000000-scan-fw-4fc9ccc9f49e637b-v001511 | 1,200,000 | 9,600,000 |

The original detector rejects the two highest rates. The experiment snapshot
extends admission and fixes three independent capacity assumptions: 23-sample
coarse-template buffers, the 1602-element fine frequency/score arrays, and the
FFT input allocation (16384 points exceeds rate/500 at 7.5 MS/s). Preserve all
original sources. Host ASan/UBSan controls must pass at all four rates first.
These fixes establish a research path, not production high-rate qualification.

Run each rate as a phase, controls then real data, in ascending rate order so
2.5 MS/s gets first priority. A scientific failure stops the remaining cases
at that rate; keep the failure and allow independent rates to be evaluated.
Incomplete strata cannot pass. Total target deadline is 850 seconds plus ten
seconds for cleanup, with a 15-second in-process alarm for each executable.
The earlier separate smoke/main time allocations are replaced by this bound.
All work remains saved-file CPU execution; no capture service or radio control
is invoked. The target address, rate plan, baseline and thresholds are fixed
before timing. run_target.py records the exact build and evaluator hashes.

## Question and scope

Does FP32 FFTW, natural-stride ingress, or their combination reduce complete
native GLRT service time on one local PLUTO+ Cortex-A9 core without changing
the supported detections? Measure the existing six-window, one-confirmation
research profile. Do not compare against the Python eleven-probe scanner or
claim acceleration of a deployed service with different scientific flags.

Input is ordinary saved CI16 files. The device is a compute target only:
no RF collection, libiio context, RX/TX buffers, tuning, FPGA programming,
capture API, deployment service, firmware update, or radio register access.
No remote production radio is part of the experiment.

## Target and containment

Local host discovery found USB 0456:b673 and interface enx00e02297811f with
host address 192.168.2.10/24. This identifies a possible local transport, not
the target IP, serial, firmware, SSH identity or readiness. Resolve those from
local USB/network metadata and an explicitly bound SSH connection before a run.
Never substitute the old 192.168.1.20 production binding.

Read CPU/kernel identity, available affinity, clock/governor, memory, filesystem
capacity and running processes. Use one available ARM core, record its index,
and set/verify affinity inside the benchmark before initialization. Require one
thread; use serial FFTW plans and execute RX0 then RX1 on the same core.
Record the actual CPU count but do not use a second core. Leave clock policy
and unrelated services unchanged. If capture or other substantial work is
active on this target, report contention and stop; do not stop services.

Use a newly created /tmp/leo-static-glrt.XXXXXX directory only. Stage one IQ
case at a time (maximum 4.8 MB), templates, executables and private libraries.
Do not install libraries globally. Check free memory against measured pilot-run
RSS plus 32 MiB headroom, and free scratch against the complete staged payload
plus 16 MiB. Retrieve receipts after each case. Remove only registered scratch
files after retrieval; retain local receipts on all failures.

## Fixed data

Main cohort: first 16 development visits (block_offset 0 through 15) in each
of four existing session blocks: 64 physical visits, 128 receiver observations.
Order each block by source_start_counter. Selection uses metadata, not scores.

| Manifest directory | Rate | Edge | Session |
|---|---:|---|---|
| ../2026_09_27_ds5_cached_tracking/dataset | 2.5 MS/s | lower | scan-fw-1a0e881391ba1d2f |
| ../2026_09_27_ds5_cached_tracking/dataset | 5 MS/s | upper | scan-fw-3ec1c634e1f48f77 |
| ../2026_09_27_ds5_cached_tracking/new_data | 2.5 MS/s | upper | scan-fw-40ebc07665464c7d |
| ../2026_09_27_ds5_cached_tracking/new_data | 5 MS/s | lower | scan-fw-e76c229e9dc498b3 |

Each visit is 120 ms, little-endian int16, shape [samples, 2 RX, 2 IQ].
Export header-free bytes on the host; do not transmit .npy headers as CI16.
Preserve rate, edge, channel, receiver, source counter and original hashes.

Manifest SHA-256 values:

- dataset/cases.json: 4874540dfe94bd5ced2d5496d6c53635de22c8f5d59d8edf0a159c62a899d401
- new_data/cases.json: b1a7a557a58de5adfe0af87e034ddde4737df18d917fc6536331146bff62a845

All 64 selected local .npy files were found and their manifest SHA-256 values
verified while writing this design. Total source size is 230,408,192 bytes;
the device does not need to hold the entire cohort. These are exposed
development recordings, not independent holdout or physical truth labels.

Run the 12 existing 2.5/5-MS/s pilot/noise/tone control cases listed in
../2026_09_27_ds5_cached_tracking/review/arm_probe/plan.json first.
Keep real and constructed results separate. Do not open additional holdout.

## Four matched implementations

| ID | Input path | FFT backend | Purpose |
|---|---|---|---|
| A | Packed receiver | FP64 FFTW | Primary realistic native reference |
| B | Packed receiver | FP32 FFTW | Isolate precision/backend change |
| C | Aligned natural dual-RX stride | FP64 FFTW | Isolate ingress change |
| D | Aligned natural dual-RX stride | FP32 FFTW | Measure actual combined gain |

Freeze identical scientific flags, exact/control templates, six screens,
one blind confirmation, search grids, nuisance treatment and thresholds.
Use the same compiler/optimization policy and Cortex-A9 hard-float target.
No fast-math addition. Record FFT plan policy and library build provenance;
verify actual FP32 NEON execution through build/disassembly evidence.
Precision conversion belongs in the timed call. This does not change every
statistic or accumulator to FP32: qualify the existing FP32 FFT bridge first.

Reuse the report-owned arm_probe/probe.c and build.py patterns in a new
experiment directory. Existing A and D executables are useful prototypes;
build B and C with the matching backend/input combinations. Preserve all old
sources and receipts. Hash-pin the new code, transitive sources, compiler,
flags, profile, templates, libraries, executables and exported IQ before timing.
Built-in FP64 is optional diagnostic context, never the primary denominator.

## Measurement protocol

1. Host-side component tests and ARM functional smoke: validate all four
   builds, exact payload size, malformed-input handling and result schema.
   QEMU may test functionality; none of its timings count as ARM performance.
2. Target controls, then one real visit from each of the four blocks. Stop on
   correctness failure, out-of-memory, affinity failure or incomplete output.
3. If the smoke passes, run the entire fixed 64-visit real cohort. Use one
   warmup and five measured complete calls per method/case. Rotate method
   order across cases as ABCD, BCDA, CDAB, DABC. Report warmups separately.
4. Time RX0 and RX1 individually and their serial sum. CLOCK_PROCESS_CPUTIME_ID
   is the primary compute metric; CLOCK_MONOTONIC measures wall latency.
   Include packing, conversion and the entire detector call. Report file
   read/page-in, initialization/planning, serialization and transfer separately.
   Do not hide per-visit work as one-time setup. Print detailed results after
   timed regions; use a warm persistent-workspace service interpretation.
5. Record stage CPU: rank, coarse, fine, fractional, conversion and nuisance.
   Explain nested timers; do not sum inclusive stages. Record RSS, faults,
   affinity, thread count and available clock readings. Keep every failed or
   negative visit in accounting; never substitute positive-only timing.

Hard limits: 15 seconds per child process, 120 seconds for controls/smoke,
600 seconds for the main phase, and 15 minutes for the whole target session
including staging. Enforce deadlines from the host and a target watchdog;
kill only experiment-owned children. Do not extend automatically on timeout.
Save partial receipts and classify the run incomplete, not a successful faster
subset. No new RF is needed at any stage.

## Predeclared assessment

Primary per-rate speedup is sum of A per-case median CPU divided by sum of
candidate per-case median CPU, over the same complete set. Report B/A, C/A,
D/A and D/C independently; do not multiply separate ratios. Report real-data
2.5 and 5 MS/s separately, then an explicitly equal-visit weighted aggregate.
Include case-level paired ratios, medians, observed p95/max wall and counts
over 100 and 120 ms for each RX and for the serial pair. These small-sample
tails are descriptive, not a real-time service guarantee.

For this numerical replacement, require unchanged activity, candidate count,
selected window, rank order and fractional/support completion versus A;
associate every reference positive within circular 2 us and physical CFO
8 kHz. Require no added positives and deterministic scientific outputs across
repetitions. Report maximum exact/control/margin/timing/CFO drift and distance
to the decision threshold, including negative and incomplete results.
Controls must retain injected associated pilots and reject noise/tone cases.
On gate failure, retain evidence and stop promotion; do not change thresholds.
Reference agreement is not a field sensitivity or false-alarm calibration.

Performance classifications after passing science:

- >=1.30x at both rates: worthwhile candidate for broader qualification.
- >=1.50x at both rates: strong first-stage result.
- 1.00--1.30x or rate-specific gains: report honestly and prioritize measured
  dominant stages; no automatic rejection of a useful rate-specific build.
- Regression: retain baseline at that rate. Do not turn a stage win into a
  whole-call claim.

If a rate has no real reference positives, label its sensitivity evidence
insufficient rather than reporting 100% retention. The constructed positives
do not fill that real-data denominator.

## Deliverables and follow-up

Produce target.json, frozen dataset/build manifests, raw per-case JSON,
checksums, failure log, summary.csv and REPORT.md. The report answers: how much
did FP32 alone save, how much did ingress alone save, what is the combined
single-core cost, did evidence change, and which stage now dominates?

Implementation still required: new four-build receipt; five-repeat probe with
verified affinity/watchdog; fixed-cohort export; local USB-target SSH runner;
four-method assessor and component tests. Hardware tests must be explicitly
marked hardware, never silently skipped. Do not execute the old remote_run.py:
it binds to a production device and capture authority, contrary to this scope.

After this experiment, choose one follow-up from measured ARM attribution:
fractional-sampling optimization if that dominates, otherwise acquisition
work reduction. Evaluate tracking in a separate chronological experiment with
empty state per session, original timestamps, fresh confirmation and charged
failed checks/blind fallback. Preserve an expiring dormant proposal only as a
search hint, never a stale detection. Do not combine tracking and FP32 changes
in the first experiment because it would obscure the source of improvement.
