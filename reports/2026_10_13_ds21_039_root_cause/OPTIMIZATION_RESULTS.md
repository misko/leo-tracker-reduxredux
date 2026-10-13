# DS21-039: optimization versus objective

The prescribed fitted-c profiles found a feasible all-band objective **774.164 below the original all-band winner** at the training-selected high-band point. This establishes an optimization deficit in the original saved solution. It does not establish localization accuracy or the global minimum of the objective. No reference positions or held observations were used.

The original low/high/all winners were selected by stationary fitted-c training objective, each at start 5. Their own-view objective and likelihood NLL replayed exactly before this experiment. Every profile used the original **all-band** native model, 43-satellite bank, 2,798 training windows, RF/time/group frame, priors and applied sampling lifts. Each anchor received the same six original all-band physical correction, satellite timing and group-nuisance starts; only vector XY changed. Geography stayed fixed. Each call retained the original 20-second/600-iteration allowance.

| Fixed training anchor | Selected start | Stationary attempts | All-band objective | Change from original | Selected KKT statistic |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original all-band winner, before profiling | 5 | Historical stationary winner | 33172.423429104 | 0 | — |
| Low-band winner | 1 | 6/6 | 36780.247959074 | +3607.824529970 | 0.000623094 |
| High-band winner | 5 | 6/6 | 32398.259712359 | **−774.163716745** | 0.000307963 |
| All-band winner | 3 | 5/6 | 33842.714337471 | +670.290908366 | 0.000647488 |

All three anchors lie within the original all-band start-5 proposal disk: 9.098660, 7.742265 and 9.292923 km from its center, respectively, against the original 25-km radius. The better high-anchor state therefore lies within the original search domain. Its improved objective is not an effect of expanding that domain.

The following costs all use the same all-band model. Low/high likelihood contributions are additive; shared timing and group-calibration priors appear once. These band costs must not be compared as if they were the separately fitted low/high models with their own frames.

| State | Low likelihood NLL | High likelihood NLL | Common-timing prior | Relative-timing prior | Group prior | Native residual RMS, Hz | Expected signal windows |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Original all-band winner | 20075.963986 | 12893.535784 | 0.119287 | 202.405030 | 0.399342 | 104.396460 | 2068.045453 |
| Cold low profile | 22211.298713 | 14362.152359 | 0.059488 | 206.337924 | 0.399475 | 116.437426 | 1484.678427 |
| Cold high profile | 19714.817054 | 12528.339701 | 0.162646 | 154.540695 | 0.399616 | 94.124338 | 2166.530716 |
| Cold all profile | 20447.966114 | 13244.028155 | 0.133134 | 150.187869 | 0.399066 | 91.267798 | 1928.327195 |

At the high anchor, the objective improves through both bands: low NLL decreases by 361.146932, high NLL by 365.196083, and total prior cost by 47.820702. The decomposition matches each selected fit objective within 7.28e−12; the low-plus-high NLL closure is exact in the stored receipts. Satellite posterior masses are conditional model assignments, not measured identities.

The lowest native residual RMS occurs in the cold all profile, despite its worse objective and smaller expected signal mass than the original solution. RMS is conditional on the model's signal assignments and does not substitute for the normalized mixture objective. Frequency residuals alone do not establish better localization.

There were exactly 18 new calls, 17 stationary outcomes, and no retries. All-anchor start 0 remained nonstationary (KKT statistic 23.937909147), with its full outcome retained. No selected outcome touched a bound. The fit phase took 253.495 seconds; summed reported optimizer time was 253.150 seconds, within the prescribed 360-second aggregate allowance.

The cold all-anchor profile cannot recover the already known original objective at precisely the same point. This demonstrates dependence on nuisance initialization and optimization path, even among stationary outcomes. The cold profiles consequently do not decide which anchor has the lowest fully profiled objective, whether the objective prefers an inaccurate location, or whether another geographic basin is better. A separate bounded amendment will test three warm profiles from the same original all-band winner and four free-geography continuations; these 18 receipts stay immutable.

Evidence is retained locally under this study: `local/profiles-v1/fits/terminal.json`, `local/profiles-v1/freeze.json` and source snapshots, `local/diagnostics-v2/optimization-baseline.json`, and `inputs-v1.json`. These raw receipts are not included in the report-only publication. The profile freeze binds 321 matching live/source-snapshot files; input and diagnostic-parent hashes also match. Implementation commits are `c88fead29` and `c6627a836`; 19 focused component tests passed, including eight profile tests rerun after the cached-point guard correction.

| Receipt | SHA-256 |
| --- | --- |
| Profile terminal | `df67a44b1c4dcb3da2797f31abd40e8c2aa47ceae005251580fc48fbadaef068` |
| Profile freeze | `6132d33a4e34d05423b39d1468d95a8cdd866182295a9c6b56046da6837bdb7a` |
| Baseline | `1d0afbc3cc65d05687ab796615452b44f57e4aa101c8e6e54f1daca58e8fd77e` |
