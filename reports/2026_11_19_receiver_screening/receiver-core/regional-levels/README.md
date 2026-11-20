# Regional CFO level from anonymous GLRT

Within a supplied 25 km square, the shared CFO receiver published **0 of 6 real roof recordings** and **2 of 2 newly simulated containing offers**, in both calibration arms. The simulated fixes were **1.28 and 2.87 km** from truth, compared with **8.00 km** for the tile centres. The free per-arc intercept control published **2 of 6 real roofs**, at 7.94 km error each, and withheld on both simulations despite finding the same two simulated coordinates. Both receivers withheld on all **four omitted offers**. [Both-arm position charts](charts/manifest.json) · [Full scores](scores.csv)

## Search and controls

The regional worker receives anonymous native GLRT, the original capture clock, one causal TLE and the offered square. It runs the preceding absolute-Doppler model over the square and four equal exterior squares centred 50 km north, south, east and west. Each uses the same 25 cell centres spaced 5 km apart. The training-ranked coarse winner within each square fixes one orbit, phase and integer alias per selected arc. Both calibration arms keep those rows while evaluating all 25 exact fixed-support sites. They choose locations on head-only RF cost. Late observations determine held evidence and publication. The directly evaluated centre uses the same support as its inside winner and is separate from the always-report-centre geographic prior in the charts. [Protocol](PROTOCOL.md) · [Implementation sources](source-lock.json) · [Prediction traces and RF profiles](positions.jsonl.gz)

The exterior comparisons normalize by the same full arc count and charge the fixed cap for missing arcs. The original numeric thresholds require both arms to have held RMS at most 750 Hz, four held orbital identities, three carriers, two RF paths and a held cost lead of at least 0.65 over a tested training-ranked rival at least 30 km away. This checks specific exterior alternatives. The nearest sampled site was 1.345 km from the real roof for all containing offers, and 1.28 and 2.87 km from the two simulated sites. The earlier worldwide run remained 363 km from the roof. The two real omitted offers had an exterior sample 1.01 and 2.16 km from the roof. The 90 km simulated omitted offers had nearest exterior samples 29.57 and 47.17 km away. [World comparison](../absolute-doppler/README.md) · [Immutable regional inputs and samples](blind-plan.json)

## Geometry and RF

The table shows medians in c0 / fitted order. “Forced” is the inside estimate regardless of publication. RF scores are in Hz. The two published free-offset roof fixes were from DS26-0122 and DS29-0519.

| Offer cohort | Receiver | Published | Forced km | Train RMS | Held RMS |
| --- | --- | ---: | ---: | ---: | ---: |
| Real containing | Shared level | 0/6 | 9.64 / 9.64 | 1,139 / 1,136 | 1,329 / 1,296 |
| Real containing | Free intercept | 2/6 | 5.51 / 5.51 | 74 / 74 | 311 / 311 |
| Real omitted | Shared level | 0/2 | 46.17 / 46.17 | 2,264 / 2,254 | 3,443 / 3,438 |
| Real omitted | Free intercept | 0/2 | 45.37 / 45.37 | 164 / 164 | 983 / 983 |
| Simulated containing | Shared level | 2/2 | 2.07 / 2.07 | 373 / 177 | 366 / 166 |
| Simulated containing | Free intercept | 0/2 | 2.07 / 2.07 | 21 / 21 | 39 / 39 |
| Simulated omitted | Shared level | 0/2 | 88.64 / 90.38 | 2,335 / 1,995 | 2,406 / 2,351 |
| Simulated omitted | Free intercept | 0/2 | 87.81 / 87.81 | 216 / 216 | 1,208 / 1,208 |

The real containing tile centre was 8.19 km from truth. Shared estimates beat the centre on 3 of 6 in both arms, and free estimates beat it on all six. Original no-repair v5, on the same six native recordings and containing offers, published all six with median **1.04 / 1.05 km** and conditional RF RMS **88 / 79 Hz**. V5 receives additional causal element history and this RF is measured on its fitted support. Both regional methods retain held RF on their own anonymous selected arcs. The original four v5 roles appear on the matched containing charts only. [Case-level RF, geometry and v5 matches](scores.csv)

In the simulations, both models found the same closest sampled locations and correctly identified all 150 individually matched held peaks across the two containing captures. The free model's exterior lead was only 0.198 and 0.215, despite its held errors of 36 and 41 Hz. Shared levels increased those leads to 0.882 and 2.516 in c0, enough to publish. Fitting the RF slope lowered shared held RMS on both simulated sites while their positions stayed unchanged. The result demonstrates regional discrimination from absolute CFO under a simulated common-clock contract. [Simulated emitter and receiver truth](synthetic-truth.json) · [Regional result and comparison receipts](scores.json)

For the real containing cases, shared identities agreed with no-repair v5 on 71 of 81 common held peaks. Free intercepts agreed on 70 of 81. This diagnostic joins exact receiver, time, RF, channel and uniquely recovered native peak rank. It covers the intersection with stable archived ownership and treats v5 as an independent reference. Every real shared-level held RMS exceeded 750 Hz, even with the better spatial coverage and high observed agreement on common points. The regional result leaves a substantial common-clock or orbital-model residual on measured data. It also leaves the unjoined arcs' identities unresolved. [Exact held points, ambiguity counts and original owner hashes](scores.json)

## Runtime and replay

The 210-line regional adapter reuses the frozen worldwide model and common numerical helpers. Each paired job evaluated 125 coarse locations and 125 exact sites per method, processing 14–16 selected anonymous arcs and 9,803–11,191 causal orbits. Median paired CPU was 4.27 s, wall time 5.96 s and peak RSS 297 MiB. The maximum paired CPU was 5.07 s. All 12 predeclared numerical jobs finished on CPU 4. [Per-job resources](scores.csv) · [Source seal](source-lock.json)

The first eight saved archive offers use the published implicit 25 km width and initially hit a missing-field error before numerical work. Before truth was opened, the adapter was corrected to use that existing default, and only those eight archive jobs were retried. The four explicit simulated-offer predictions were retained from the first run. The blind plan records both source digests and the original results remain sealed. [First attempt seal](first-prediction-lock.json) · [Final seal](prediction-lock.json)
