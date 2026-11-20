# Causal orbit continuity on held native Doppler

The receiver withheld **all seven queries**. Only DS29-0519's blind training winner predicted coherent late signals. It predicted 18 native visits across three held blocks, with zero hits from the ±12 kHz placebos. All 18 votes came from one orbit hypothesis. The held geographic lead was +0.00297 against the +0.03 requirement. On the same early inputs, deranging the late visits removed all 18 hits. [Position and support scores](scores.csv) · [Support figure](continuity-support.png)

The first 65% of native probes supplies anonymous arcs. Physical inverse orbit proposals generate worldwide receiver candidates. Each candidate fits four bounded early receiver/RF-band drifts and binds an early arc to a causal orbit if its shape wins by the frozen margin. A robust wrapped level learned on the same receiver and RF is then fixed. The candidate and all rivals predict actual late acquisition visits using the same orbits, oscillator slopes, intercepts and RF. Each site learns its own hypotheses on the same early data. A held peak never triggers another orbit search. [Prospective protocol](PROTOCOL.md) · [Source lock](source-lock.json)

Only scheduled above-horizon visits with the same receiver and RF enter the forecast denominator. A supported orbit needs at least five coherent hits spanning five seconds. Each native receiver visit contributes once. Both frequency placebos use the same schedule and orbit. The late cyclic permutation changes only the held peak lists. The scoring code verifies that its corresponding original had identical early coordinates, arc/identity metrics and eligible late opportunities. Fixed `c` is absorbed by each learned same-RF intercept, leaving no independent fitted coefficient. The numerical `c=0` arm includes all forced coordinates. `fitted_c` is explicitly unavailable. [Numerical predictions](positions.jsonl.gz) · [Prediction lock](prediction-lock.json)

| Recording and evaluator scope | Blind forced error, km | Held opportunities | Held coherent / placebo hits | Blind blocks / orbits | Coherent hits at given survey |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS26-0261 containing | 17,602.27 | 2,191 | 0 / 0 | 0 / 0 | 19 |
| DS29-0519 containing | 7.80 | 2,568 | 18 / 0 | 3 / 1 | 0 |
| DS26-0070 omitted | 11,199.09 | 1,692 | 0 / 0 | 0 / 0 | 0 |
| DS29-0316 omitted | 9,958.15 | 2,054 | 0 / 0 | 0 / 0 | 0 |
| DS26-0261 late derangement | 17,602.27 | 2,191 | 0 / 0 | 0 / 0 | — |
| DS29-0519 late derangement | 7.80 | 2,568 | 0 / 0 | 0 / 0 | — |
| DS26-0048, fresh hash reserve | 9,629.12 | 2,415 | 0 / 0 | 0 / 0 | 0 |

These are five independent acquisitions at one measured site, including two authentic omitted offers and the prospectively hash-selected DS26-0048. The offer enters scoring only. DS29-0519's blind estimate falls inside the containing offer. Its 443.15 Hz held CFO RMS describes the 18 coherent matches. The strongest rival was on the 25 km ring. The earlier free-rematch receiver also withheld at this same 7.80 km forced endpoint. It scored completely late shapes against any visible orbit, so its normalized shape loss has a different meaning. The original four v5 options use the containing offer. On the fresh recording their errors were 0.536 km with `c=0` and 0.424 km with fitted `c`. [Both calibration views and matched controls](charts/README.md)

## Exact-coordinate diagnostic

A separate post-seal audit inserted the known survey coordinate and repeated the same early orbit and frequency binding. It produced 19 late hits on DS26-0261, all within one block and one hypothesis, with 626.81 Hz held RMS and zero placebo hits. The other four inputs had no coherent hits at the actual site, including DS29-0519. At survey, 10–12 links per recording still provided 1,518–2,793 geometrically visible opportunities. This shows a shortage of transferable orbit and frequency hypotheses even when the search receives the correct site. The 18 blind matches on DS29-0519 are evidence for one coherent trajectory under that hypothesis and model. They give no independent orbit identity verification. [Privileged diagnostic protocol](DIAGNOSTIC.md) · [Privileged results](survey-diagnostic.json)

Each blind run used 18–20 early arcs, 360 exact trial sites and 2.69–3.40 million visible early orbit/profile comparisons. The seven bounded workers used 12.75–18.76 CPU seconds, 18.55–39.11 elapsed seconds and 369–419 MiB peak RSS. The 259-line estimator reuses causal propagation, exact Doppler and physical proposal code. All three component tests passed, including a planted orbit with a fixed wrapped frequency, ambiguity rejection and a sparse coincidence control. [Scoring receipt](score-lock.json)
