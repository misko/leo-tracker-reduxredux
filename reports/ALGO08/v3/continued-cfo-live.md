# Live CFO admission on one resident signed member

Continuation reduced actual 20 ms CFO calls from **45 to 7**. Refinement CPU fell from **36.020 to 8.294 ms**, with **0.744 ms** spent advancing and checking continuation over all 102 probes. The verified selected-packet seal was **22.678 ms** earlier. Fresh process elapsed improved only **0.812 ms** on this pair. [Frozen protocol](continued-cfo-live-protocol.md) · [Signed comparison and clocks](measurements/continued-cfo-live.json.gz)

Both processes traversed the original staged 64-visit DS30-0169 member with the same unmodified receiver and fixed-epoch library. Exactly 51 visits were admitted, yielding 16 full and 86 short-primary native calls. Every pre-refinement native factor, all 64 decoded window digests, admitted opportunities and delivery clocks matched. The two input files, compressed payload and signed index, had all **19,295** pages resident at every checkpoint. No reconditioning or original archive access ran.

| Measured boundary | All paid | Continued |
| --- | ---: | ---: |
| Short refinements | 45 | 7 |
| CFO edits | 35 | 6 |
| Actual refinement CPU, ms | 36.020 | 8.294 |
| Online continuation CPU, ms | — | 0.744 |
| EOF held-cycle CPU, ms | 5.427 | 2.471 |
| Authenticated acquisition CPU, ms | 328.844 | 303.306 |
| Worker start through selected packet seal elapsed, ms | 600.737 | 578.059 |
| Fresh process through exit CPU, ms | 699.678 | 675.180 |
| Fresh process through exit elapsed, ms | 716.150 | 715.338 |
| Whole process input blocks | 16 | 0 |

The acquisition stage already includes the native refinement and online decision work. The EOF policy clocks include the original held-cycle selection, signed packet rebinding and its decision receipt. The seal verifies immutable file bytes. Interpreter startup, wrapper output and process exit remain in the external clock. Variation outside the seal boundary accounts for most of the difference between the two observed wall savings. This one all-paid-first pair supplies a bounded CPU price for the actual gate and no full-recording timing estimate.

Both routes selected **unfiltered**, with history gains of **−2.058 and −3.884 nats** on radios 0 and 1. Each sealed **56** factors. Each paid correction and each unchanged full anchor matched. The gated packet has the original CFO on precisely the **29** skipped edits that the all-paid route changed, with median absolute change **61.14 Hz** and maximum **178.00 Hz**. All other fields matched the independent continuation projection, with distinct policy-bound detector identities. This prefix supplies no position, RF fit or calibrated solver comparison. [Earlier saved whole-packet price and weak fit](continued-cfo.md)

Run `continued_cfo_live_trial.py run NEW_TMPFS_ROOT` under the shared Gauss lock with CPU 2, nice 15, I/O priority 7 and one numerical thread. The archive-readable account uses the existing signed tmpfs member and the pinned original member wrapper. The modified test boundary waits for the real EOF selector and stops before invoking the solver. Eleven component and adjacent tests passed. No additional timed pair ran. [Driver](continued_cfo_live_trial.py) · [Component tests](../../../tests/pipeline_eval/test_continued_cfo_live_trial.py)
