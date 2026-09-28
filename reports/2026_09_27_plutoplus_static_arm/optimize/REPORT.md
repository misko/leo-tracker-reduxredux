# Exact ARM kernel optimizations and concurrent qualification

Latest: [40% headroom optimization](GOAL40.md) achieved 42.7–44.1% CPU0
headroom in two recorded-cadence capture runs. The `rankunroll` results below
are the earlier exact-arithmetic baseline.

Target: PLUTO+ 192.168.1.15. Date: 2026-09-27.

**The optimized dual-RX worker keeps up with the recorded adaptive cadence
under live capture contention, with about 21% CPU0 headroom in this short test.**
Use CPU0 for GLRT and CPU1 for capture/networking, with RAM buffering for
bursts. This does not establish a strict 120-ms result deadline or an integrated
live-GLRT feedback pipeline.

The `rankunroll` candidate preserves the original six-window, two-receiver
scientific workload. It combines a register-resident integer ranking fold,
exact bounded int64-to-FP64 conversion using native ARM instructions, and
compiler loop unrolling. It is an isolated benchmark build, not a deployed
production change.

## Full saved-IQ qualification

All 104 cases completed on the target. All **1,040 receiver results matched
the original D results exactly**, excluding timings. The same source passes
104 host ASAN/UBSAN cases. Real-input CPU means of each case's five-repetition
median, per dual-RX 120-ms visit:

| Sample rate | Original D | Candidate | Reduction |
|---|---:|---:|---:|
| 2.5 MS/s | 108.06 ms | 93.40 ms | 13.6% |
| 5 MS/s | 202.10 ms | 172.05 ms | 14.9% |
| 7.5 MS/s | 310.34 ms | 266.59 ms | 14.1% |
| 10 MS/s | 389.36 ms | 331.85 ms | 14.8% |

The 2.5/5 cohorts have 32 real cases each; 7.5/10 have eight each. Each rate
also has six noise/pilot/tone controls. All positive/negative decisions remain
unchanged. The 10-MS/s real cohort contains no confirmed positives; planted
pilot controls supply positive coverage at that rate.

The persistent contention cohort uses eight of the 2.5-MS/s cases and has a
slightly higher mean: original D 109.28 ms versus candidate 94.95 ms in the
stateless probe. Do not compare that subset directly with the 32-case mean.

Evidence: `rankunroll-all-summary.json`, `work/rankunroll/arm-all/`,
`work/rankunroll/host-check/`, and `work/rankunroll/arm.build.json`.
Host sanitizers validate the source; ARM disassembly and target results
qualify the NEON path and final ARM compiler options.

## Experiments retained separately

- Ranking loop alone saves approximately 8 ms on the eight real 2.5-MS/s cases.
- Exact conversion alone saves approximately 3.6 ms; the combination is about
  11.5 ms faster. Compiler unrolling adds approximately 3 ms.
- An experimental FP32 differential dot product passed scientific tolerance
  gates but saved only about 1 ms. It is excluded from the selected candidate.
- A separate exact sample-index experiment saves about 2 ms versus the
  rank/conversion build. It is not included in `rankunroll` or its concurrent
  results; see `AUDIT.md` for the public offset boundary caveat.
- Broad profiling identifies about 10.6 ms in GLRT interpolation/correlation,
  2.9 ms rotation setup, 2.8 ms ceiling/short FFT, and 2.4 ms final FFT work,
  averaged over the eight real cases. These figures include timer overhead
  and explain where further optimization could help; they are not savings.

## Reproduction

`build.py`, `prepare_conversion.py`, and the source snapshots retain exact
compiler commands and source/binary hashes. The baseline is the frozen
`../build-snapshot.tar.gz` and `/tmp/leo-static-arm15-20260927-v3` during this
session. `arm_check.py` executes saved inputs only. All-rate qualification:

```sh
.venv/bin/python reports/2026_09_27_plutoplus_static_arm/optimize/arm_check.py rankunroll --all --output-name new-arm-all
```

Use a fresh output name. `persistent/README.md` describes building and running
the separately named persistent worker. Passing `--capture` performs a new
bounded live receive-only campaign; omitting it uses saved IQ only.

The numerical audit and known limitations are in `AUDIT.md`. The original
capture/CPU/SD benchmark and full alternatives are in `../concurrent/REPORT.md`.

## Concurrent fixed-120-ms qualification

The optimized persistent worker ran 500 dual-RX jobs with a 45-second live
receive-only adaptive scan overlapping the run. GLRT used CPU0; IIO and the
temporarily relocated Ethernet IRQ used CPU1. Capture delivered 330/330 visits
without gaps, skips, invalid results or cancellations. Receiver settings,
kernel buffers and IRQ affinity were restored exactly.

All 1,000 saved-IQ receiver results matched original D exactly. During capture
overlap (373 fully completed jobs), GLRT CPU averaged **103.33 ms**, versus
118.33 ms before the kernel changes under the same IRQ arrangement. CPU0 busy
fell from 99.9% to **88.25%**, with CPU1 at **39.82%**.

Published response averaged 108.22 ms, with p95 **130.87 ms** and maximum
143.73 ms. **53/373** results exceeded the 120-ms period. Queue delay during
overlap averaged 1.23 ms and peaked at 23.81 ms, rather than accumulating.
Across the entire 500-job run (including capture setup/restoration), there
were 61 misses and maximum queue delay was 85.64 ms. This is a substantial
throughput improvement, but does not qualify a strict 120-ms result deadline.

Evidence: `persistent/runs/opt-rankunroll-combined-irq1/summary.json` and
`irq-affinity.json`. GLRT still consumes resident historical IQ; the live scan
provides genuine CPU/memory/network contention, not live GLRT feedback.

A separate 45-second default-IRQ run confirms why placement matters even after
optimization: mean overlap GLRT CPU was 112.54 ms, CPU0 was 97.80% busy,
and 217/372 overlapping published results missed 120 ms (p95 161.11 ms).
All 330 capture visits and all 1,000 saved receiver comparisons passed.
Its evidence is `persistent/runs/opt-rankunroll-combined-default/`.

## Recorded adaptive cadence

The exact 330 arrival offsets recorded by the earlier scan-only benchmark
(mean spacing 136.16 ms, minimum 22.58 ms) were replayed against saved IQ while
a fresh 45-second live scan ran independently. All 330 GLRT jobs completed;
all 660 receiver results matched exactly. The concurrent scan delivered
330/330 visits with exact radio/kernel-buffer/IRQ restoration.

Across 289 fully overlapping jobs, mean GLRT CPU was **104.18 ms**, CPU0 busy
was **79.18%** and CPU1 busy **42.03%**. Thus measured CPU0 headroom was
**20.82%**, compared with about 10% for the original D worker on this recorded
schedule. This is headroom at the observed cadence, not at continuous 120-ms
input pacing.

Published response averaged 175.48 ms, p95 **265.67 ms**, maximum 332.26 ms.
The first/last 50 jobs' mean queue delays were 73.44/67.39 ms; final queue
delay was 0.04 ms. Maximum queue delay across all jobs was 239.93 ms. The queue
did not grow persistently in this short replay, but bursts still prevent a
120-ms result deadline (191/289 overlap results exceeded it).

Evidence: `persistent/runs/opt-rankunroll-recorded-cadence/`. Its binary and
arrival-schedule hashes are recorded in `run.json` and the worker build
receipt. This schedule comes from the earlier scan, not the new scan's causal
arrival stream. The live controller continued to use its existing energy
feedback. Longer stability and integrated feedback remain unqualified.

The three new campaigns total 135 seconds of RX-only acquisition and
990/990 delivered capture visits. All 2,660 concurrent saved-IQ receiver
comparisons matched exactly. Twenty-nine component tests pass, plus the standalone
250,118-value conversion/disassembly check. No production services or firmware
were changed; temporary interrupt affinity was restored after every IRQ run.

## Options for fitting the pipeline

1. Preserve dual-RX evidence: select the exact optimized kernel, keep one
   persistent GLRT worker on CPU0, place capture/network work on CPU1, and
   buffer burst arrivals in RAM. This has the strongest direct evidence.
   A production integration must process each live visit and measure feedback
   latency, not just replay saved inputs under contention.
2. If strict 120-ms results are required, continue optimization toward
   80–90 ms under capture load. The selected kernel still needs approximately
   13–23 ms of additional reduction to reach that target. Rank/confirmation
   reuse across tracked visits is a promising separate algorithmic experiment,
   with mandatory fresh-confirmation and reacquisition checks; its savings
   have not been measured here.
3. A reduced-evidence fallback is online GLRT on one receiver, with the second
   receiver analyzed selectively or offline. The earlier concurrent benchmark
   measured about 64 ms and 64% CPU0 busy, but this does not provide continuous
   dual-RX analysis and needs a separately validated selection policy.
4. Higher sample rates retain scientific support but do not fit one 120-ms
   dual-RX analysis per 120 ms on this core. Host offload, validated decision
   decimation, or explicitly reduced analysis cadence need separate evaluation.
   Firmware on this device advertises native live adaptive 2.5/10-MS/s support;
   saved-file 5/7.5-MS/s qualification does not establish live capture support.
5. Keep continuous raw dual-RX IQ off the current SD interface. The measured
   sustained 12.13 MB/s is below the required 20 MB/s even at 2.5 MS/s.
   Network streaming, selected recordings or reduced-volume products are the
   practical options with current hardware. SD capacity is not bandwidth.
