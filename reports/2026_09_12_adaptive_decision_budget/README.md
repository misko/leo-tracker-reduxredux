# Adaptive decision budget: decimation and fewer probes

2026-09-12. Saved-IQ investigation only. No RF collection, deployment, migration
or change to the running scanner. Reproducible driver:
[`tools/investigate_adaptive_decision_budget.py`](../../tools/investigate_adaptive_decision_budget.py).

## Result and recommended next experiment

Keep recording and offline analysis at native 10 MS/s. Prototype a separately
versioned **5 MS/s decision stream with progressive 20 ms probes**: stop once
a positive is confirmed; otherwise expand from one to three to six windows.
Only filter the windows actually evaluated. A partial evaluation without a
positive remains UNKNOWN; it cannot inherit the old demotion semantics.

This is a candidate for ARM qualification, not a production-ready detector.
In particular, the desktop timings below do not establish radio capacity.

## What was actually tested

- Two complete production captures: RX1 `scan-hop-b80df494d948f78a` and RX0
  `scan-hop-b96cfdd5fb0ee91c`, both recorded at 10 MS/s.
- Four sweeps per capture, frozen before inspecting decisions: 40, 110, 180,
  250. All eight targets at each point: 64 independent recorded dwells,
  32 per receiver. These selected sweeps are not a contiguous scheduler replay.
- Each 120 ms dwell evaluated at both 5 and 2.5 MS/s. No threshold tuning:
  fractional completion, exact score >= 0.175, margin >= 0.025.
- Reference: OR of six independent 20 ms confirmations at filtered 5 MS/s.
  It produced 30 positive dwells. These are reference candidate decisions,
  not RF truth, decoded signals or verified satellite identities.
- Existing native classifier flags from the sealed runtime algorithm manifest,
  compiled on x86-64 with the portable native FFT. ARM production uses FFTW;
  its exact numerical, transport and performance qualification is still needed.

The live worker already screens six windows and performs only **one** expensive
confirmation. Fewer confirmations alone cannot improve that budget. The study
therefore compares its full screening with direct temporal probes.

## Measured component costs and decision retention

CPU estimates include measured filtering/quantization plus native confirmation
costs. Sparse variants sum independently measured window costs; they are not
end-to-end worker/IPC latency. Setup, disk reads, integrity verification and
warmup are excluded. Native C execution uses the CI16 path, including its
integer nuisance calculations. CPU load on the shared host was not controlled.

| Decision rate and policy | Median CPU ms/dwell | P95 CPU ms/dwell | Retained of 30 reference positives | Additional positives |
| --- | ---: | ---: | ---: | ---: |
| 5M: full screen, confirm best one | 25.34 | 26.24 | 23 | 0 |
| 5M: first 20 ms only | 4.24 | 4.49 | 24 | 0 |
| 5M: two windows, 0 and 60 ms | 8.16 | 8.52 | 25 | 0 |
| 5M: three windows, 0, 40, 80 ms | 12.16 | 12.54 | 27 | 0 |
| 5M: progressive, stop on positive | 23.06 | 24.18 | 30 | 0 |
| 5M: all six, reference | 30.77 | 31.74 | 30 | 0 |
| 2.5M: full screen, confirm best one | 17.71 | 18.17 | 22 | 1 |
| 2.5M: three windows | 9.65 | 9.92 | 23 | 2 |
| 2.5M: progressive, stop on positive | 18.91 | 19.58 | 25 | 3 |

The 5M progressive policy averaged **15.68 ms** and **3.94 windows per dwell**.
Its median is higher because most sampled dwells required all six windows.
The order was 0, 40, 80, 20, 60, 100 ms; this component-cost experiment assumes
the dwell is available and does not claim early feedback before the dwell ends.
All-six preservation follows from expanding to the same reference evaluations;
it is not an independent sensitivity result. Candidate selection/CFO can still
differ when multiple windows contain different candidates.

Reducing 5M to 2.5M is not numerically neutral: even its all-six policy retained
25/30 reference positives and produced three additional positives. Neither the
missing nor additional decisions have been labelled as RF false negatives or
false positives. This warrants holdout work before choosing the narrower stream.
Likewise, first-window's 24/30 versus ranker's 23/30 is a small-sample result,
not evidence that fixed first-window selection is generally superior.

## Filter and temporal accounting

The prototype uses causal polyphase FIR filtering, unity DC gain, Kaiser beta
8.6, followed by rounded CI16 quantization. No amplitude renormalization or
threshold adjustment is applied. Factor two uses 129 taps and a 2 MHz cutoff;
factor four uses 257 taps and a 1 MHz cutoff. Native group delays are 64 samples
(6.4 us) and 128 samples (12.8 us), respectively.

History resets after each hop. No future samples or another target's IQ are
used. Sparse filtering reads the actual preceding FIR history within the same
dwell and exactly reproduces full-dwell filtered CI16 for every tested window.
The initial transient and delayed final samples remain explicit; conversion of
timing evidence must subtract group delay and exclude unsupported boundary
spans. No measured clipping occurred in the 128 real-data rate/dwell evaluations.

The first experiment filtered every 120 ms even for a single probe, costing
about 25.5 ms at 5M on this host. Avoiding that unnecessary full-dwell filtering
was more valuable than removing the screen itself (about 0.4 ms). The original
run is retained at `/var/tmp/leo-adaptive-decision-budget-20260912`; the table
uses `/var/tmp/leo-adaptive-decision-budget-20260912-v2` with sparse filtering.

## Controls and implementation checks

Twelve independently generated 10M pilot cases cover both edges and each of the
six temporal windows. Both rate variants recovered all 12 in the correct window.
Twelve additional cases cover white noise, an in-band tone and an out-of-band
tone that would alias without filtering: neither rate produced a positive.
This is a smoke test, not a statistically adequate false-alarm qualification.
It also illustrates the danger of fewer fixed probes: a one-window policy has
no access to injected pilots confined to the other five windows.

Ten component tests pass: causal delay, passband/alias rejection, quantization
and polyphase equivalence, true sparse-filter history, physical-RX shape checks,
probe selection and threshold accounting. Ruff and whitespace checks pass.
Golden scientific fixtures were not changed.

Direct native-10M timing was intentionally not fabricated. The on-radio native
classifier still rejects that rate and contains 23-sample pilot scratch arrays;
simply removing rate checks would be unsafe. The already deployed native-10M
offline analyzer is a different implementation and is not a fair timing proxy.

## Next bounded work

1. Freeze a 5M progressive decision configuration, including temporal masks,
   FIR coefficients, delay/boundary rules and partial-result semantics. Retain
   native 10M recording and the chosen physical RX throughout.
2. Implement and benchmark the exact causal decimator plus classifier on ARM
   using saved IQ, with native counters and a bounded per-dwell budget. Measure
   CPU, wall time, IPC, memory, deadline/UNKNOWN counts and positive-rich versus
   negative-heavy arrivals. The latter exercises the all-six worst case.
3. Preserve the current scheduler's complete 120 ms dwell and freshness bounds.
   Short-circuiting computation must not shorten capture or claim full search
   coverage. New coverage masks require versioned SDK/wire evidence, since the
   current frame adapter requires all-six search and one ranked confirmation.
4. Test a held-out sample selected independently from this development set.
   Freeze quality and latency gates before evaluating it. Validate classifier
   behavior at both RX choices, CFO extremes, weak signals and structured
   interference. Do not infer unsampled adaptive RF from fixed-scan replay.
5. Only after the ARM and holdout gates pass, use the plan's separately authorized
   bounded shadow/adaptive canaries and verify duty, deadlines, recording and UI.

No claim of 95% adaptive duty or sustained real-time ARM performance is made
by this desktop investigation.
