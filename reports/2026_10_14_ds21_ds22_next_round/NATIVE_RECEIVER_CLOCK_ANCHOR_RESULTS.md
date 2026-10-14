# Native-clock C selects a better independent-band basin

On DS22-001, the native-clock model selects the lower-band geographic anchor after profiling and releasing all three predetermined starts. Configured-reference distance improves from 19.428852 to 6.928778 km. All six fits independently pass the unchanged stationarity criterion. The result remains far above the target, and DS22 reference remains configured-unconfirmed.

| Starting geography | Final objective | Training NLL | Posterior RMS Hz | Final KKT | Configured distance km | Training-selected |
|---|---:|---:|---:|---:|---:|---|
| Accepted full-band native-clock fit | 41418.038343 | 41017.333838 | 133.582149 | 0.000622562 | 19.428852 | No |
| Original independent CH1–4 C fit | 40896.026658 | 40601.209027 | 120.017311 | 0.000310513 | 6.928778 | Yes |
| Original independent CH5–8 C fit | 42821.263599 | 42499.152203 | 124.920124 | 0.000102550 | 5.411226 | No |

The independent half-band positions were fixed in the earlier sealed experiment, without reference-based choice. Only starting geography differs across arms. Each begins with the same accepted full-band native-clock calibration, fitted c, group offsets and satellite timing. Each first fits with geography fixed, then releases geography within a 25 km disk centered on its own anchor. All use the same full-band observations, bank, likelihood and priors. Selection is the lowest independently stationary training objective, sealed before reference evaluation. The nearer upper-anchor result is not substituted for that winner.

The original C anchor/checkpoint experiment preferred its farther full-band state. With native receiver clocks and the present initialization, the lower-band basin wins instead. This supports an interaction between calibration flexibility and basin search; it does not isolate a single causal change, because the fitting paths and additional numerical work differ. The earlier common-clock cold search, warm initialization and this six-call anchor probe are separate experiments with additional budgets, not equal end-to-end search costs.

Each new call retained the 20-second limit and imposed a hard 600-objective-evaluation cap including derivative work. The fixed-geography variant explicitly includes geography in the affine tangent constraints if numerical finishing is needed. The common gradient core and original independent KKT checks are unchanged. The actual full experiment completed in 95.277941 seconds with six calls and no retries, held scoring, or reference-derived initialization. Its original sources and failed prior controls remain intact.

This remains substantially worse than the original B-all result on the same sample. The next diagnostic checks exact transfer of B's full fitted physical/calibration/timing state into the native C model, rather than geography alone. Matched augmented half-band models have not been run, so no claim that the new model beats its own half-band variants is justified.

Source `e5edac034`; the new real-objective fixed-geography integration test and Ruff pass, alongside the previously qualified gradient core. Receipts: `local/ds22-native-clock-anchors-v1` and post-seal `local/ds22-native-clock-anchor-comparison-v1/report.json`. Terminal SHA256 `d62208e564da3891adcf76c57cd291742e4ee843fd38b05483edcfd7b6f7cc93`; seal SHA256 `57374ee6f9d2f335e2b7877c5d3faa7a122aa97a4c6c19174cd9680891a8428f`.
