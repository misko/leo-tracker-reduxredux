# Doppler turn times from anonymous GLRT

**No measurable CFO turn was found.** The sign-symmetric linker supplied 384 real arcs from four archived rooftop recordings and 48 arcs from two freshly simulated sites. All 432 had negative overall slope. Across 15,639 seconds of retained arc support, zero arcs proposed an interior turn at the frozen training threshold and zero passed independent interleaved-sample validation. The position stage was never attempted. Both calibration arms retain null positions and null forced guesses. [Measured support figure](turn-support.png) · [Sealed arc inventories](positions.jsonl.gz) · [Benchmarked stage charts](charts/manifest.json)

| Query group | Offers | Unique captures | Distinct captured arcs | Held measured turns | Causal orbit–site pairs | Modeled sign reversals | Modeled two-sided turns |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Real containing | 2 | 2 | 192 | 0 | 7,705 | 23 | 0 |
| Real omitted | 2 | 2 | 192 | 0 | 6,629 | 19 | 0 |
| Simulated containing | 2 | 2 | 48 | 0 | 5,036 | 31 | 0 |
| Simulated omitted | 2 | Same two | Same 48 | 0 | 4,961 | 27 | 0 |

The real linker retained its full 96-arc cap per recording. The same simulated peak documents were processed under both offer conditions, so the measured counts are counted once per site. Distinct predicted orbit–site pairs refer to the five generic sites in each offer and can include the same satellite at several sites. The 2 s causal TLE sweep found 100 short, above-horizon sign reversals across all eight offers. Zero predicted windows had sustained, visible opposite slopes greater than 100 Hz/s on both sides. The modeled result separates sparse physically measurable turns near the offers from the empirical linker cap. [Complete tally](scores.csv)

## Observation and validity

The anonymous tracker has symmetric Doppler-rate support and retains confirmed arcs without a curvature prefilter. Each attempted event uses only measured CFO samples on both sides of an interior crossing. Training and held fits use alternating actual points. Independent side slopes must have opposite signs, agree on direction, and place the crossing within two seconds of each other. Nearby measured points must also support the turn. Timing is invariant to a fixed offset on each RF lane, including the fitted constant coefficient of RF. The calibration arms have identical observability evidence and endpoints. The component tests recover both planted extrema and reject monotone, extrapolated, gapped and training-only alternatives. [Frozen protocol](PROTOCOL.md) · [Source and dependencies](source-lock.json)

DS26-0122 and DS29-0247 have authenticated original containing-offer comparisons. Original no-repair v5 published both at 0.75 and 1.32 km in c0, and 0.75 and 1.46 km with fitted c. Their figures include all four original v5 roles. DS26-0070 and DS29-0316 use the earlier frozen truly omitted offers. No containing v5 endpoint is shown as an omitted-offer reference. The simulated labels and seeds were opened after sealing to validate their independently drawn sites and the offer relations. [Position comparison manifest](figures.json) · [Input and offer seal](blind-plan.json) · [Simulation truth and seed](synthetic-truth.json)

Eight jobs completed with median **1.58 CPU seconds** and **3.16 elapsed seconds** per job. Maximum resident memory was **190 MiB** under the 512 MiB address-space limit. The gate stopped soft orbit association and position evaluation for lack of replicated turn times. One distinct remaining hypothesis is the observed time of most negative Doppler rate. It is a landmark on a monotone CFO curve and remains invariant to a per-arc constant or affine oscillator term. An identifiability test for that landmark would need independently bracketed curvature sign changes and causal orbit-vs-orbit timing separation. [Resource and gate receipt](scores.json)
