# Simultaneous satellite-pair Doppler

The receiver found persistent same-window candidate pairs in both captured roofs and completed four c0 regional fits across their containing and displaced offers. **All four withheld.** The fitted RF arm was **unavailable** because each witnessed pair had identical RF. The emitted waveform supplied no persistent pair and withheld before the fit on both offers. [Co-observation and conditioning figure](paired-support.png) · [Both-arm position charts](charts/manifest.json) · [Per-offer scores](scores.csv)

## What is simultaneous

For two candidate transmitters observed in the same receiver at the same instant, write the difference as

```text
CFO_A(t) − CFO_B(t) = Doppler_A(t) − Doppler_B(t)
                    + transmitter offset difference + c × (RF_A − RF_B)
```

RF is in GHz in the calibration term. Any common receiver-frequency term cancels at each sample, including nonlinear drift. An unknown integer difference from the native CFO ambiguity and an unknown constant transmitter difference are absorbed by one pair intercept. All admitted pairs have equal actual RF, so the calibration column vanishes. Even a static unequal-RF pair would leave the term confounded with an unconstrained pair intercept. A fitted coefficient would require varying RF contrast under a shared offset reference. The receiver also requires the same physical RX and band path. It uses no relative clock assumption between receivers. [Support protocol](PROTOCOL.md) · [Geometry protocol](GEOMETRY-PROTOCOL.md)

There were **zero same-path simultaneous different-RF windows** among **29,386** exact windows across the three unique captures. This is a tuning-geometry fact. The roof pairs do span multiple RF lanes over the complete recordings. The same-time cancellation remains valid because each individual subtraction is within one tuned receiver window.

| Unique capture | Native RF lanes | Separate gated two-peak windows | Persistent paired arcs | Exact pair witnesses | RF lanes used by pairs | Train / held blocks |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DS26-0261 | 8 | 983 | 18 | 325 | 7 | 6 / 3 |
| DS29-0519 | 8 | 1,335 | 27 | 509 | 6 | 6 / 3 |
| Emitted Qin waveform | 8 | 113 | 0 | 0 | 0 | 0 / 0 |

Pairs require two distinct gate-passing peaks with wrapped CFO and frame-epoch separation in exactly the same sample window. Both candidate paths must recur with at least ten shared witnesses over at least twelve seconds. The receiver keeps counters and individual ranks, and merges duplicate RX support for a given block and RF lane. Separated raw candidates can be false peaks or duplicate signal explanations. The waveform study emits at most one intended transmitter on a particular RF lane at an instant. Its separated candidates did not become paired support. [Exact witness archive](positions.jsonl.gz) · [Previously emitted waveform provenance](../../track-recovery/waveform-site/README.md)

## Paired geometry and the individual-arc control

For each admitted pair, the causal model evaluates the full measured CFO difference against two distinct anonymous orbits. It profiles one intercept and two regularized orbital phases. A soft orbit-pair mixture updates horizontal position using the exact differential line-of-sight spatial derivative, starting from five generic in-tile positions. Held blocks select tentative pairs on their own prefixes and test the late points, excluding confidently trained identities. The clock control uses the same full raw request and tile but fits separate raw passes with a shared oscillator slope per receiver path. Its RF is an individual-arc shape residual. The paired RMS measures a different physical observable.

| Offer | Centre error (km) | c0 paired forced error (km) | Shared-clock forced error (km) | Paired held differential RMS (Hz) | Shared-clock held shape RMS (Hz) | Paired profiled radius (km) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DS26-0261, containing | 8.19 | 6.21 | 2.98 | 279 | 117 | 61.13 |
| DS29-0519, containing | 8.19 | 7.89 | 1.48 | 167 | 203 | 58.53 |
| DS26-0261, displaced | 57.96 | 51.01 | 46.20 | 397 | 399 | 67.19 |
| DS29-0519, displaced | 59.41 | 47.36 | 47.48 | 233 | 1,012 | 52.90 |
| Emitted waveform, containing | 8.94 | — | 21.53 | — | 395 | — |
| Emitted waveform, omitted | 14.02 | — | 23.30 | — | 428 | — |

Despite modest conditional held differential RMS, **zero** held putative pairs met the orbit confidence threshold. Each selected site also lost to a separated alternative, with held mean cost advantages of −0.15 to −0.84. The best phase-profiled weakest-axis radius was 52.90 km, against the 12.5 km publication limit. These are separate ambiguity and conditioning failures. A useful common-clock cancellation therefore did not give sufficient evidence to localize from anonymous pairs here. [Fit and geometry receipts](paired-positions.jsonl.gz) · [Full RF and position table](scores.csv)

The omitted real offers were generated using fixed hash bearings and a 55 km displacement from the public original tile centres. They reuse the original detector and orbital inputs. Survey coordinates entered only after sealing. Original no-repair v5 returned c0 estimates of **1.39 and 0.25 km** on the original two containing requests. All four original roles appear on those authentic requests. The shared-clock control also withheld all six observed offers in both arms. The previously installed waveform baseline is retained separately on its original simulation offers, with its distinct RMS and calibration contract. [Blind input plan](blind-plan.json) · [Omitted and containing score bindings](generated-omitted-queries.json)

## Cost and verification

The 152-line co-observation component took a median **0.27 CPU seconds** across the six requests. The 226-line position component took **1.07 CPU seconds** median over the four exact-ledger worker jobs. Those jobs retained 216 or 324 causal pair candidates per offer, used one thread and shared the 512 MiB address-space limit. Peak process memory across scope and both model stages was **189 MiB**. The scope worker also ran the existing individual-arc control, and its total elapsed range includes host scheduling and the archived input handoff. No IQ or waveform was regenerated. Five tests cover recurrence on exact windows, staggered and same-frame negative controls, oscillator and RF cancellation, and prefix-only two-phase fitting. [Support seal](prediction-lock.json) · [Geometry seal](geometry-lock.json) · [Chart score seal](score-lock.json)
