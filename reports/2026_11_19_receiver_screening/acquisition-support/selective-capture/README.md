# Selective capture-era detector replacement

The causal trigger improved median position error across these four recordings at both budgets. It left the fitted-calibration target count at **2 of 4**, the same as the pure-wide control. The two held recordings moved in opposite directions, and the high budget substantially worsened the most inaccurate development case. All 16 phase-release position services published both arms. [Protocol](PROTOCOL.md) · [All scores](scores.csv)

| Input policy | Median position error, zero / fitted (km) | Within 10% of original v5, zero / fitted | Median conditional Doppler RMS, zero / fitted (Hz) |
| --- | ---: | ---: | ---: |
| 0% capture · complete wide | 0.898 / 0.871 | 3 / 2 of 4 | 89.00 / 88.96 |
| Causal · up to 1 per 128 | 0.881 / 0.863 | 2 / 2 of 4 | 88.86 / 88.83 |
| Uniform · same low budget | 1.014 / 0.995 | 3 / 2 of 4 | 88.66 / 88.60 |
| Causal · up to 1 per 16 | 0.806 / 0.793 | 2 / 2 of 4 | 88.07 / 88.02 |
| Uniform · same higher budget | 1.097 / 1.018 | 2 / 2 of 4 | 88.72 / 88.65 |
| 100% capture · complete capture-era | 0.727 / 0.717 | 4 / 4 of 4 | 88.04 / 88.06 |

Both arms used the same selected observations within each method. Each budgeted variant met the 5% threshold on two recordings in each arm. Relative error reports compare against the original no-repair v5 option using each recording's own geographic reference. The four recordings came from one physical roof. [Prediction seal](prediction-lock.json) · [Grouped summary](summary.json)

| Recording | Role | Fitted wide | Fitted causal, 1/128 | Fitted causal, 1/16 | Fitted complete capture |
| --- | --- | ---: | ---: | ---: | ---: |
| DS26-0036 | Development | 0.935 km | 0.928 km | 0.829 km | 1.196 km |
| DS29-0082 | Development | 2.346 km | 2.345 km | 3.484 km | 0.516 km |
| DS26-0237 | Held | 0.323 km | 0.335 km | 0.490 km | 0.262 km |
| DS29-0174 | Held | 0.806 km | 0.797 km | 0.757 km | 0.918 km |

## Selection and achieved spend

The selector uses only the wide detector's current margins and physical peak branches. Either receiver can propose a visit. It takes the first eligible visit in each credited block of admitted visits. Empty or below-half-gate results earn no challenge by themselves. The first block earns credit without spending, so the number of challenges stays below the budget on every chronological prefix. Each selected visit switches both receiver probes, with their candidate lists and ranks intact. The paired uniform control distributes the same number of replacements across credited blocks and uses their midpoint visits. A compatibility preflight compared archive schemas, clocks and exclusions before sealing. The selector read only wide candidates and sealed its decisions before the factor mix loaded capture-era candidate lists. Geographic scoring began after the prediction seal. [Selection and exact visit identities](selection-lock.json)

| Recording | Admitted visits | Low budget, actual | Higher budget, actual |
| --- | ---: | ---: | ---: |
| DS26-0036 | 6,765 | 52 · 0.769% | 375 · 5.543% |
| DS29-0082 | 4,868 | 37 · 0.760% | 283 · 5.813% |
| DS26-0237 | 6,766 | 52 · 0.769% | 386 · 5.705% |
| DS29-0174 | 6,704 | 52 · 0.776% | 381 · 5.683% |
| Total | 25,103 | 193 · 0.769% | 1,425 · 5.677% |

Every replacement changed its complete stereo data. At the low budget, the causal replacement added a positive to five formerly zero-positive visits and removed all positives from five. The uniform control added one and removed nine. At the higher budget, causal added 25 and removed 55, while uniform added 17 and removed 74. These are gate outcomes from the paired detector factors. [Factor counts and routing provenance](fit-plan.json)

## Real waveform checks and measured work

Each SHA-selected witness replayed the same actual saved IQ on both frontends and reproduced both archived receiver rows exactly. Two witnesses came from each band and from each budget. Native capture CPU on the selected visits ranged from 0.497 to 1.407 s. Wide CPU ranged from 13.46 to 17.47 ms. [Witness roster](waveform-plan.json) · [DS26 development](DS26-0036-waveform.json) · [DS29 development](DS29-0082-waveform.json) · [DS26 held](DS26-0237-waveform.json) · [DS29 held](DS29-0174-waveform.json)

The work estimate includes a measured wide call on every visit, the measured selector cost, and measured capture-detector CPU per replacement. The whole wide archives averaged 21.01 CPU ms per admitted visit. Across the four recordings the low and higher policies estimate **32.21** and **103.51 CPU ms** per visit, respectively, using the independently measured capture-lineage means. Substituting the four selected witness clocks as a sensitivity gives 29.79 and 85.87 CPU ms. Both estimates exceed the 20 ms visit interval. Causal and uniform have equal modeled cost within each case and budget. The detector cost model excludes archive I/O and the position solver. [Per-recording measured clocks and costs](detector-cost.json)

The actual position services started from complete mixed factor documents with authenticated parents, a common causal catalogue inventory, identical track configuration and the original offered region. They used the standalone phase-release worker with a 512 MiB enforced cgroup cap and zero swap. The measured cgroup peaks ranged from 258.88 to 344.59 MiB. Pure-wide and pure-capture endpoints come from the recorded compact cavity controls with the same numerical solver and verified factor and request digests. The [phase-release comparison](../../detector-origins/pressure/README.md) qualifies disposal of completed likelihood models and preserves the original fitting and admission calculations. [Actual service receipts](fit-receipts.json)

The standard screening figure IDs are `selective_capture_first_128`, `selective_capture_first_16`, `selective_capture_uniform_128` and `selective_capture_uniform_16`. The recorded position comparisons use conditional factor replacement. The waveform witnesses and CPU model cover the separate front-end boundary.
