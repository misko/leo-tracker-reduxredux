# Crossing native detector fields on identifiable candidates

The two detector outputs rarely admit a unique candidate match at the same visit and receiver. The strict gate-independent rule identified 53–101 pairs per recording, across 42,162–63,485 complete candidates per source. Those pairs cover 0.8–2.0% of winning observations. The factor swaps test only that common support. [Protocol](PROTOCOL.md) · [Exact match counts](matching.json) · [Frozen map](matches.jsonl.gz)

## Where candidate identity breaks down

The eligible edge requires a reported fractional epoch within two samples after frame wrapping and a Doppler difference within 1 kHz after alias wrapping. An accepted pair has degree one on both sides of this graph. Neither gate flags nor scores, rank or geographic inputs enter the match. Duplicate or near-duplicate aliases therefore remain outside the crossing whenever a physical candidate cannot be selected unambiguously. The denominator for matched winners is the original gated winner count at that source. [Per-recording audit](matching.json)

| Recording | Matched pairs | Complete candidates, capture / ordinary | Matched winners, capture / ordinary | Matched gate disagreements | Probes with ambiguous edges |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS26-0036 | 88 | 59,973 / 59,622 | 51 of 3,395 / 43 of 3,610 | 3 | 3,014 |
| DS29-0082 | 53 | 42,162 / 43,375 | 38 of 1,868 / 34 of 2,044 | 2 | 1,545 |
| DS26-0237 | 66 | 60,306 / 60,148 | 37 of 3,740 / 32 of 3,927 | 3 | 3,288 |
| DS29-0174 | 101 | 61,128 / 63,485 | 42 of 4,018 / 40 of 4,134 | 0 | 3,642 |

Across the two development recordings, 83–90% of gated winners have a counterpart within the joint tolerances. Most of those edges are ambiguous. Multiple raw candidates can report the same fractional epoch when their integer sample and fractional offset cancel. Several CFO branches can also wrap onto nearby values. Candidate order differs even among the accepted pairs, with original rank retained in only 21–37 pairs per recording. All eight matched gate disagreements were capture-era passes and ordinary failures. The complete native inputs showed the opposite count imbalance, with thousands more ordinary passes. Unique matches represent a small, selected portion of those inputs. [Whole-factor comparison](../../next/input-factor-comparison/README.md)

## Controlled inputs

Each run kept the recipient candidate roster, unmatched candidates, probe times, calibration arms, track settings and full causal TLE history. Copying donor scores can change the gated winner without changing stored recipient CFOs. Copying alias-aligned CFOs keeps the gated winner and its score. The joint swap uses the same frozen pairs to measure their interaction. Each hybrid is a diagnostic factor document labeled with parent identities and a fresh content hash. It was evaluated directly by the stored-factor solver.

## Development results

All 12 development services completed. The numbers are changes from each unmodified recipient, shown as zero/fitted. Positive error means farther from the roof reference. [Position and conditional RMS scores](scores.csv)

| Recording | Recipient | Score and gate error change (m) | CFO error change (m) | Joint error change (m) |
| --- | --- | ---: | ---: | ---: |
| DS26-0036 | Capture-era | −25 / −26 | −26 / −28 | −35 / −44 |
| DS26-0036 | Ordinary | +56 / +17 | +1,475 / +1,401 | +767 / +713 |
| DS29-0082 | Capture-era | +14 / +14 | +106 / +61 | +103 / +44 |
| DS29-0082 | Ordinary | +51 / +52 | −118 / −120 | −78 / −82 |

For DS26-0036 on ordinary factors, replacing 43 winning CFO values with capture-era measurements moved error from 0.218/0.180 km to 1.693/1.581 km. The median absolute CFO change was 177.7 Hz and the maximum was 831.0 Hz. The same observations remained admitted, with 3,610 observations and a track count falling from 104 to 102. The joint swap reached 0.986/0.893 km. Its error increase was 0.763/0.705 km smaller than the sum of the individual geographic-error changes.

DS29-0082 on ordinary factors showed a different direction. The CFO-only swap reduced error by 118/120 m and the joint swap reduced it by 78/82 m. Its whole factor-source change had increased error by 2.221/2.138 km. The crossed subset establishes receiver sensitivity to these specific observations. It leaves the contribution of unmatched candidates and other detector changes unresolved. [Whole factor-source changes](../../next/input-factor-comparison/scores.csv)

## Reserve results

All 12 reserve services completed. The same diagnostics found ordinary CFO sensitivity on both recordings, with different responses to the joint substitution. [Position and conditional RMS scores](scores.csv)

| Recording | Recipient | Score and gate error change (m) | CFO error change (m) | Joint error change (m) |
| --- | --- | ---: | ---: | ---: |
| DS26-0237 | Capture-era | +1 / +2 | −39 / −30 | −32 / −23 |
| DS26-0237 | Ordinary | +81 / +83 | −112 / −129 | −141 / −159 |
| DS29-0174 | Capture-era | +1 / +1 | +67 / −20 | +73 / −30 |
| DS29-0174 | Ordinary | −1 / +1 | −352 / −368 | +14 / +15 |

The CFO-only swap on ordinary DS29-0174 moved error from 1.161/1.224 km to 0.809/0.856 km. Copying scores as well returned error to 1.175/1.239 km even though none of its 101 matched candidates changed gate flags. With the same candidate roster, score and CFO substitutions can interact through winning peak selection and downstream tracking. The joint ordinary-recipient geographic-error interaction was +0.367/+0.382 km on this recording. [Interaction ledger](summary.json)

## Conditional Doppler RMS

Conditional RMS for each hybrid is reported in hertz. Its observations and associations follow the resulting tracking graph. [Exact RF values and resources](scores.csv)

| Recording | Recipient | Score and gate RMS change (Hz) | CFO RMS change (Hz) | Joint RMS change (Hz) |
| --- | --- | ---: | ---: | ---: |
| DS26-0036 | Capture-era | −0.172 / −0.170 | +4.229 / +4.224 | +4.381 / +4.371 |
| DS26-0036 | Ordinary | −0.409 / −0.399 | +1.262 / +1.264 | +1.335 / +1.323 |
| DS29-0082 | Capture-era | −0.277 / −0.282 | +1.607 / +1.667 | +1.243 / +1.301 |
| DS29-0082 | Ordinary | +1.655 / +1.644 | −2.426 / −2.434 | −2.193 / −2.194 |
| DS26-0237 | Capture-era | +0.017 / +0.017 | +1.613 / +1.647 | +1.517 / +1.553 |
| DS26-0237 | Ordinary | −5.280 / −5.287 | +0.959 / +0.947 | −1.158 / −1.189 |
| DS29-0174 | Capture-era | +0.036 / +0.036 | +4.570 / +4.591 | +1.148 / +1.160 |
| DS29-0174 | Ordinary | −0.409 / −0.399 | +0.090 / +0.090 | −0.269 / −0.266 |

## Runtime and scope

All 24 first-attempt services published both arms. They ran on CPU 10 or 11 with a real 512 MiB cgroup, zero permitted swap and the 135 s deadline. Observed wall time was 33.59–86.06 s and cgroup CPU usage was 32.68–75.84 s. Cgroup memory peak ranged from 257.6 to 316.1 MiB. The services began at stored factors. All four recordings came from one roof and the strict matching rule left more than 99.8% of complete candidates outside each cross. The measured effects apply to the swapped fields on accepted pairs with the original recipient support. [Input and source lock](plan.json) · [Measured resources and endpoints](results.jsonl.gz) · [Prediction lock](prediction-lock.json) · [Development and reserve figures for both arms](plots/index.html)
