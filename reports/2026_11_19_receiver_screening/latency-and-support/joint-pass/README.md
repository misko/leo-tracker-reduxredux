# Joint Doppler shapes with shared receiver-path drift

Both oscillator models produced forced estimates and **withheld on all eight offers**. The shared model forced **2.98 and 1.48 km** error on the two real containing requests, compared with **8.19 km** for their tile centres. Every clock-profiled spatial radius exceeded the **12.5 km** gate. The closest real fit with three independent held candidate families still had a **32.1 km** conditional radius. [Conditioning and held RF figure](joint-pass-support.png) · [Both-arm position charts](charts/manifest.json) · [Full scores](scores.csv)

## Shared oscillator model

The receiver links anonymous GLRT peaks in disjoint elapsed 30 s blocks and keeps at most one pass arc per actual RX/band path per block. It tracks a free intercept per pass and a single frequency slope shared across passes on the same receiver path. The control fits an independent slope for each arc. The per-pass intercept exactly absorbs fixed-carrier `c`, so the two calibration arms have the same forward model and endpoints. The fixed drift prior and bounded linearized orbital phase keep short segments from using unconstrained time and clock adjustments. [Frozen protocol](PROTOCOL.md) · [Source closure](source-lock.json)

Each arc supplies up to six anonymous causal orbit alternatives. Soft orbit responsibilities and an explicit no-match component enter one profiled spatial/oscillator normal equation. Each elapsed block has one unit of training weight across its lanes. This keeps slope information across multiple passages while fitting site and clocks together. The previous cross-track identity receiver inferred a peer clock before fitting a separate site model, while the two-pass geometry method removed a free slope from every arc before intersecting two lines. This method uses five free-position starts and clock-only fits at fixed rivals. Its information matrix combines all training blocks. [Earlier cross-track clock experiment](../../detector-origins/blind-identity/README.md) · [Earlier two-pass intersections](../../arrival-and-timing/pass-hypotheses/README.md)

Held arcs come from untouched blocks and physically corresponding paths with at least two training blocks. A held prefix selects an anonymous tentative orbit and phase, excludes confident training NORADs, and leaves the late points to test prediction using the frozen shared clock. The independent control estimates its own free slope on the held prefix. No held data chooses the location. Site comparisons use the same centre-shortlisted orbit bank on the fitted location, separated converged candidates and fixed alternatives, including exterior points. The observed NORAD assignments are physical hypotheses. [Prediction and clock traces](positions.jsonl.gz)

## Geography and held radio evidence

All coordinates below are forced. The radius is a local weakest-axis standard deviation derived after eliminating estimated oscillator slopes, conditional on the retained paths, the fixed phase linearization and the fitted orbit responsibilities. Held RF RMS is reported in Hz after the pass intercept, slope and phase, with no geographic information entering its measurement.

| Offer | Centre km | Shared / independent forced km | Shared / independent held RF Hz | Shared / independent radius km |
| --- | ---: | ---: | ---: | ---: |
| DS26-0261, containing | 8.19 | 2.98 / 3.50 | 117 / 140 | 32.1 / 38.3 |
| DS29-0519, containing | 8.19 | 1.48 / 0.89 | 203 / 198 | 41.0 / 45.2 |
| DS26-0070, omitted | 51.23 | 40.15 / 40.15 | 979 / 965 | 22.6 / 32.7 |
| DS29-0316, omitted | 55.19 | 41.71 / 42.96 | 1,158 / 909 | 32.5 / 30.3 |
| Emitted Qin waveform, containing | 8.94 | 21.53 / 21.22 | 395 / 254 | 46.4 / 42.8 |
| Emitted Qin waveform, omitted | 14.02 | 23.30 / 22.78 | 428 / 423 | 35.9 / 43.4 |
| Independent factor simulation, containing | 8.00 | 16.49 / 16.31 | 255 / 252 | 34.4 / 37.2 |
| Independent factor simulation, omitted | 90.00 | 72.47 / 72.47 | 447 / 239 | 50.4 / 49.9 |

The shared slope retained **87–100%** of the weakest training spatial singular magnitude after clock elimination, compared with **63–96%** for independent slopes. Its local radius improved on five of eight offers. Every radius remained over the gate. Only DS26-0261 had three held families. It also had a positive separated-site held lead of 3.29 and 117 Hz held RMS. Lower conditional ambiguity from a shared oscillator therefore helped a specific measured fit without certifying its geometry. Both simulated containing offers had a worse forced error than their original tile centres. [Geometry, drift and full RF statistics](scores.json)

The two real containing requests have all four matched original v5 options. Original no-repair v5 published those at **1.39/1.36 km** and **0.25/0.32 km** in c0/fitted order. Reported v5 RF uses the original fitted support. The independent emitted-waveform site uses the original stock native GLRT document and its two original offers. Its historical phase release returned **1.02/0.75 km** on the containing offer. The separate factor simulation uses an earlier blind native-format capture at another location and its genuine 90 km displaced offer. This distinguishes simulated-factor transfer from actual detector output on a synthesized waveform. [Waveform provenance](../../track-recovery/waveform-site/README.md) · [Factor simulation provenance](../../receiver-core/regional-levels/README.md)

Each paired worker used 14–28 training arcs and 132–240 shortlisted orbit shapes in total. The standalone estimator is 327 Python lines plus shared native parsing, linking and geometry. Median paired time was **3.07 s CPU and 4.57 s elapsed**, with maximum RSS **184 MiB** under the 512 MiB address-space limit. All eight jobs completed. Three component tests cover the prefix-only clock fit and exact calibration cancellation, oscillator-position confounding and soft orbit ambiguity. [Frozen roster](blind-plan.json) · [Prediction seal](prediction-lock.json) · [Score and figure seal](score-lock.json)
