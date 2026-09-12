# ARM progressive decision prototype: real-time gate failed

2026-09-12, approximately 19:52–19:57 UTC. The prototype was implemented and
tested using saved IQ on production radio `.20`, exact serial
`1040005e0b100007100010000bf33a5d4d`, while it was idle between scheduled scans.
No RF collection, firmware change, service change, migration change or adaptive
profile activation occurred. Acquisition and API remained active afterward.

## Outcome

**Do not enable this implementation for adaptive hopping.** Even one 20 ms
decision probe requires about 190 ms of ARM CPU after optimization. The fixed
scan produces a valid visit about every 126 ms, so this single-worker path
cannot keep up. Negative-heavy work requires all six probes and takes about
1.14 seconds, also exceeding the existing one-second feedback freshness bound.

| ARM workload | Initial prototype mean CPU | Optimized mean CPU |
| --- | ---: | ---: |
| One probe, positive immediately (4 cases) | 219.94 ms | 189.99 ms |
| Six probes before completion (10 cases) | 1,273.76 ms | 1,140.75 ms |

The other two cases needed three and four probes. The 16-case set is balanced
across RX0/RX1, lower/upper edge, and reference-positive/reference-negative dwells,
with two cases per stratum. Selection came from the earlier development replay;
it is not a held-out sensitivity evaluation or representative population mix.

All 16 unbounded results matched the 5M six-probe desktop reference decisions
(eight positive, eight without a positive). This is numerical decision agreement,
not RF truth or satellite identification.

With a **100 ms soft CPU budget**, all 16 cases correctly returned UNKNOWN and
set `budget_exceeded`. Actual CPU was 180.02–200.01 ms: a probe is nonpreemptible,
so the prototype detects an overrun after that probe. This is explicitly not a
hard execution-time guarantee. It correctly prevents a late positive or partial
miss from becoming an adaptive decision, but cannot provide useful throughput.

## Implemented research path

- C entrypoints in `src/leo/analysis/native_presence/progressive_decision.{c,h}`.
  They are not wired to the production SDK, capture adapter or daemon.
- Causal 10-to-5 MS/s, 129-tap FIR with actual preceding history within the same
  dwell, 64 native-sample group delay, FP32 coefficients/accumulation, and CI16
  output. The ARM implementation uses NEON.
- Evaluate temporal windows in order 0, 40, 80, 20, 60, 100 ms. Stop on a positive;
  otherwise expand, subject to the compute budget. Retain explicit evaluated and
  positive window masks. The entire captured dwell is supplied to this replay;
  it does not claim feedback before dwell completion.
- Existing 5M native classifier, sealed runtime numerical flags, templates and
  thresholds. ARM uses the same FFTW library as the deployed bundle, SHA-256
  `311b6ee1acd0aee1c1db9b7f9e8a41d4a918463b70cce441aad5f4679665eef4`.
- Bounded standalone replay process: maximum 64 input cases, 100-second wall
  alarm, 85-second CPU limit and 160 MiB address-space limit. Actual workload
  used 16 cases. No IIO or device interfaces are opened.

The initial ARM result showed that the filter dominated cost. Disassembly
confirmed per-component scalar `nearbyintf` calls in the hot loop. The optimized
NEON path keeps reduction, clipping and nearest-even rounding in vector registers,
removing those calls for all but the short initial boundary. This reduced cost
but did not meet the real-time gate. Six-probe optimized filtering still averaged
747.74 ms; confirmation averaged approximately 393 ms.

ARM first-window filtered output was compared component by component against the
FP64 Python reference for every case. Maximum discrepancy was one CI16 LSB.
The host tests also cover the first, interior and final windows, full-scale input,
causality, negative completion, early-positive exit and over-budget UNKNOWN.

## Validation and limits

- Six new native component tests plus ten prior decision-budget tests passed.
- An ASan/UBSan desktop replay of all 16 saved cases passed without diagnostics.
  That exercises the scalar path; the NEON path was checked on the actual ARM.
- Two unbounded ARM runs preserved numerical decisions; the final bounded run
  verified overrun handling. Raw JSONL, build receipts and selection manifest
  are saved with this report. Failed intermediate data preparation (using a
  non-context-manager reader as a context manager) was fixed before replay.
- SSH streamed the saved data; input loading, first-window parity checks and
  stdout are outside reported DSP timing. No RF/IRQ load was modeled. CPU and
  wall timings are reported separately; no claim of paced queue qualification
  is made. The idle-radio DSP result already fails capacity and freshness gates.
- The temporary replay files were placed only in a new private `/tmp` directory;
  they were not registered as services or substituted for the production worker.

## Next design decision

The next experiment should target **one useful decision probe below roughly
100 ms on ARM**, including filtering, before considering any progressive
expansion. The existing confirmation alone costs roughly 60–70 ms in the
one-probe cases, leaving only about 30–40 ms for filtering and overhead.

That requires a materially cheaper decimator (for example, a measured shorter
or multistage filter with new passband/alias and holdout checks), or a cheaper
decision statistic. Simply changing the declared sample rate or widening the
worker timeout does not solve the measured capacity deficit. Switching directly
to 2.5M also needs qualification: the desktop study already found changed
decisions, and its longer anti-alias filter has not been timed on ARM here.

Even if one probe fits, six-probe expansion on every negative dwell cannot be
assumed sustainable. A new admission/coverage policy must bound negative-heavy
work and keep unexamined coverage UNKNOWN. Any change to miss/demotion semantics
must be explicit and versioned. Keep the working fixed 10M scanner selected
until this gate is passed, then resume held-out replay and bounded shadow work.
