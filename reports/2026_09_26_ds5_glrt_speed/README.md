# DS5: routes toward near-real-time ARM GLRT

2026-09-26. Recommendation: retain exact/control GLRT as the final evidence
check, reduce how often it needs a blind search, and optimize the native
screening and fractional-pilot work. A faster detector that discards supported
signals is not a successful optimization.

## What was actually tested

The frozen DS5 manifest contains 42 scans, 93,033 complete visits and 11,163.96
seconds of valid IQ. Visits are 120 ms. Rates are 2.5 MS/s (14 scans), 5 MS/s
(10), 7.5 MS/s (9), and 10 MS/s (9).

The bounded experiment used two deterministically selected scans:
`scan-fw-03f629ba67a8af0b` at 2.5 MS/s and
`scan-fw-3159ec54906a6800` at 5 MS/s. Four chronological visits per scan,
both receivers: 16 receiver/visit cases. Selection did not use detector scores.
Recording manifests, compressed chunks and decompressed IQ were SHA-256
checked against the frozen inventory. No RF collection or production change.

We built the deployment checkout's existing native research detector with its
`arm-presence-native-tone-ci16-v1.json` defines and builtin FFT. This is not an
attestation of the binary that originally collected DS5. Compiler, source and
binary hashes are in `dwell.so.build.json`. The test compares six-window
screening plus one blind confirmation against the same screening plus one
confirmation seeded by the 512-bin screen's timing proposal. One warmup per
method, three measured repeats, alternating method order: 96 measured runs.

| Desktop median kernel wall time per receiver/120 ms visit | 2.5 MS/s | 5 MS/s |
|---|---:|---:|
| Screen + blind confirmation | 0.951 ms | 1.661 ms |
| Screen + screen-seeded confirmation | 0.576 ms | 0.880 ms |
| Apparent speedup | 1.65× | 1.89× |

**The seeded shortcut fails the evidence comparison.** Blind confirmation has
seven cases with completed fractional confirmation and margin above the
existing research 0.025 threshold; seeded confirmation retains zero of those
seven. These are reference-relative cases, not seven independently verified
satellites. Seeded and blind runs select the same window, but different timing
and CFO candidates. Even a three-sample seed displacement fails one strong
case. Faster runs also sometimes omit final fractional confirmation, so these
ratios are not equal-work acceleration measurements.

All candidate values and selected-window masks repeat identically over the
three repetitions. This checks repeatability, not detector calibration.
Raw results are in `results.json`; the runnable experiment is `run_probe.py`.
The runner has a 180-second alarm and exclusive output creation; preserve the
existing receipt before choosing a new output directory for another run.

These are **x86 desktop kernel measurements**, excluding archive reads,
decompression, setup, capture, queueing, publication and downstream tracking.
The native binding explicitly rejects 7.5 and 10 MS/s. We did not quietly
resample those DS5 strata or claim ARM latency. Only two scans were sampled;
this is a feasibility probe, not full-DS5 recall validation.

## Where to spend effort

1. **Separate discovery, confirmation and tracking.** Blindly acquire unknown
   signals, then carry timing, frequency, frequency rate and uncertainty per
   receiver/channel/edge across visits. Search a small neighborhood while
   uncertainty is low; broaden or reacquire after a gap, innovation failure or
   retune uncertainty. Retain several hypotheses around ambiguities. Carry
   frequency/timing predictions, not assumed carrier phase through a retune.
   DS5 rejects blindly trusting the cheap screen's single epoch; use calibrated
   track predictions or multiple independently supported proposals instead.

2. **Make scans adaptive to both information and compute.** Reserve a fixed
   exploration share and a maximum revisit interval so weak/new signals remain
   discoverable. Spend extra confirmations on ambiguous or changing targets;
   use fewer updates on predictable strong tracks. Treat skipped/unprocessed
   visits as unknown, never absence. Schedule on source time with bounded job
   age, not a growing FIFO. Start replay with, for example, 10–20% exploration
   as an experimental parameter, not a qualified operating value.

3. **Use a narrow decision-band stream.** Test anti-aliased 2.5-MS/s decision
   processing for 5/7.5/10-MS/s recordings while retaining the original IQ for
   detailed measurements. Input sample work could drop by 2×/3×/4× respectively;
   these are sample-count ratios, not promised end-to-end speedups. Preserve
   the pilot band and filter delay/source-counter mapping. Compare against
   native-rate evidence on the *same* recording; DS5 rate groups are different
   recordings. Existing decision-decimator code should be inspected and reused
   before adding another decimation path.

4. **Optimize the ARM hot path, especially fractional sampling.** In this
   probe, blind-confirmation median CPU costs for coarse/fine/fractional stages
   are 0.271/0.132/0.229 ms at 2.5 MS/s and 0.567/0.262/0.393 ms at 5 MS/s.
   Screening adds about 0.231/0.258 ms. These are desktop diagnostics, and
   separate medians do not form an exact additive decomposition. Profile the
   same cuts on ARM before ranking assembly work. Prototype FP32/NEON for
   pilot products, interpolation and FFTs; retain wider accumulation or final
   FP64 verification where necessary. Precompute interpolation weights and
   rotations for repeated geometry, fuse conversion/derotation/correlation,
   reuse aligned scratch and FFT plans, and avoid full-IQ passes. Several
   integer-NEON and rotation-cache optimizations already exist: measure the
   current baseline before claiming them as new.

5. **Reduce search evaluations without reducing useful aperture.** Use a
   coarse frequency grid and local peak refinement, or direct selected-bin
   evaluation for a very narrow predicted CFO range. Benchmark the crossover
   against FFTs. Larger zero-padding only samples the response more finely;
   it does not add signal observations. Keep competing peaks until confirmation
   rather than committing early to the strongest cheap proposal.

6. **Progressive evidence and safe pruning.** Try short initial support and
   extend only ambiguous cases. With a valid upper bound on the remaining
   correlation, reject impossible candidates early without changing the final
   decision; compare unnormalized powers when denominators can be shared.
   Early acceptance, shortened support and approximate pruning need separate
   threshold/false-alarm calibration. Always apply equivalent search treatment
   to exact and rolled-control evidence.

7. **Alternative scouts and more ambitious options.** Differential/repetition
   statistics, PSS timing, sparse pilot subsets, quantized or one-bit proposal
   kernels, and learned proposal ranking can feed exact GLRT confirmation.
   Test sensitivity to tones, interference and weak signals; a scout failure
   is not proof of absence. If measured ARM cost remains too high, consider
   FPGA decimation, pilot products and short accumulations, sending compact
   sufficient statistics to ARM. Offload must retain the timing/CFO hypothesis
   coverage needed by the final statistic; a single wrong accumulator cannot
   be repaired later. This is a larger architectural experiment, not a first
   step or a reason to change firmware now.

## Real-time budget and DS5 qualification

At roughly 2,215 visits per 300-second capture, the arrival interval is about
135 ms. A single worker processing both receivers serially gets about 67.5 ms
per receiver on average before other costs. A useful provisional target is
under 100 ms p99 **combined compute per visit**, leaving capture/scheduling
headroom; that target is not the total result latency. A detector that waits
for all 120 ms of IQ cannot report before that acquisition interval completes.
Partial-window decisions may provide earlier feedback but change the evidence
available to the detector.

Queue stability requires average service time below the arrival interval;
p99 age, worst bursts, capture drops and per-target coverage must also pass.
For two serial receivers, budget their sum, not each independently. Reserve
actual CPU/I/O capacity for recording. Do not count unscreened visits as a
throughput success. Historical ARM measurements from September 10 report
84.49 ms CPU p99 at 2.5 MS/s and 169.34 ms at 5 MS/s on confirmation-bearing
jobs; these are different inputs/build context, not present DS5 benchmarks.

Run the next experiments in this order:

1. Freeze whole DS5 sessions for development and held-out validation, covering
   every rate, edge and receiver. Add bounded real positive, weak, ambiguous,
   tone and null/control cuts; existing GLRT misses are not noise truth.
2. Compare native baseline, accurate seeded tracking with blind fallback,
   multiresolution/multiple proposals, and decision-band decimation. Keep the
   quality-versus-compute frontier, not just the fastest point. Measure margin,
   CFO/timing changes, retained tracks, reacquisition time and control outcomes.
3. Replay chronologically with original arrivals and only past evidence.
   Record full service cost, decision age and target coverage. Saved DS5 can
   evaluate policies on recorded visits; it cannot supply RF for hypothetical
   retunes that were never recorded. Do not claim counterfactual scan recall.
4. Run only the finalists as short saved-IQ ARM replays, recording processor,
   available cores, clock, compiler/backend, memory and concurrent capture load.
   Cap each experiment to minutes. No new RF is needed for the first rounds.

The immediate best experiment is **accurate prediction + bounded confirmation
+ blind fallback**, paired with a **2.5-MS/s decision stream**. Simply replacing
blind acquisition with the current single screen seed has already failed here.
No near-real-time ARM achievement is claimed by this report.

## Implementation and external references

- The host GLRT already has exact FFT and autocorrelation backends:
  `docs/analysis/glrt-exact-transform-integration-plan.md` and
  `reports/2026_08_22_t3_glrt_hardware_execution_alignment.md` in this repository.
- The embedded implementation inspected is under
  `/home/mouse9911/gits/leo-adaptive-position-deploy/src/leo/analysis/native_presence/`;
  `dwell.c` supplies seeded and blind routes and `presence.c` the final scoring.
- Historical ARM timing: the deployment checkout's
  `reports/2026_09_10_scanner_lnb_live_checkpoint.md` and
  `reports/2026_09_10_scanner_cooperative_skips_checkpoint.md`.
- [Arm CMSIS-DSP](https://arm-software.github.io/CMSIS-DSP/main/) documents
  Cortex-A and NEON implementations; benchmark compatible FP32 kernels against
  the existing backend rather than assuming a library swap wins.
