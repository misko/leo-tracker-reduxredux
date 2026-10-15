# Band detectability: conditional predictive support on A053, negative transfer on A035

Band contrast improves A053's twofold predictive conditional-CFO NLL by **158.837155**, but worsens A035 by **469.017885**. All eight fixed-position fits passed the unchanged independent stationarity gate. This supports further A053 investigation only; it does not establish a universal band model or any localization improvement.

These are **conditional development comparisons at already data-selected geographies**. Physical/geographic states, shared-q warm starts, discovery, candidate banks, calibration frames and nodes came from full-window current training fits. Both models share this information. Opposite-fold scoring is therefore not unbiased external validation or untouched heldout accuracy. No original held/locked observations, reference coordinates or new RF were used.

| Case / fitted fold | Shared predictive NLL | Contrast predictive NLL | Contrast − shared | Low-band gap | High-band gap |
|---|---:|---:|---:|---:|---:|
| A035 / 0 | 15557.408588 | 16118.290670 | +560.882082 | +250.524271 | +310.357811 |
| A035 / 1 | 17392.781027 | 17300.916830 | −91.864197 | −48.385376 | −43.478821 |
| A035 / both | 32950.189615 | 33419.207500 | **+469.017885** | +202.138895 | +266.878991 |
| A053 / 0 | 11522.429818 | 11416.504789 | −105.925029 | −31.569974 | −74.355055 |
| A053 / 1 | 10671.959969 | 10619.047843 | −52.912126 | −85.115537 | +32.203411 |
| A053 / both | 22194.389787 | 22035.552632 | **−158.837155** | −116.685511 | −42.151644 |

A053 improves both receivers in both folds: RX0/RX1 gaps −53.415761/−52.509268 on fold0 and −29.983650/−22.928476 on fold1. Its high-band fold1 regression prevents a claim of improvement in every band/fold. A035 fold0 loses on both receivers (+489.968566/+70.913516), while fold1 improves both (−49.812175/−42.052022).

The predictive signal/clutter masses are posterior quantities, not measured detector truth. On A035 fold0, contrast reduces signal mass by112.875288 low and132.276119 high; its density is worse on both bands. On A053 fold0, low/high signal mass rises28.485465/9.255047; fold1 low rises12.877536 while high falls4.707266. Each arm still fixes the same full-bank detection budget1.6; contrast redistributes satellite propensities independently by band, not total detection budget. These observations do not isolate a missing band-budget parameter from calibration/timing or association changes, and do not justify tuning that budget from fitted posterior mass.

All fits retain exact common fixed XY, complete original calibration/clock/timing/shared-q seed, own25km A035 or50km A053 disk, full frame and candidate bank55/59. Contrast starts at zero by duplicating the shared coefficients. Both arms use smooth visibility width1e−5, unit shared/contrast prior sigmas and effective coefficient bounds±2; no bound/prior/width was changed after outputs. Full-training high fractions .410388716890/.318716577540 are fixed across folds. The shared fit uses the diagonal-prior port; contrast uses the matrix-prior wrapper. No generic hard-model Recorded reconstruction occurs.

| Case / fold / arm | Training J | Training NLL | Prior | Strict KKT | Actual target calls | Numerical seconds |
|---|---:|---:|---:|---:|---:|---:|
| 035 / 0 / shared | 15340.403968 | 15106.156205 | 234.247763 | .000895113 | 375 | 5.210 |
| 035 / 0 / contrast | 15182.992361 | 14967.782640 | 215.209721 | .000023919 | 405 | 6.220 |
| 035 / 1 / shared | 13106.413709 | 12906.509373 | 199.904336 | .000842892 | 371 | 4.758 |
| 035 / 1 / contrast | 13042.109988 | 12828.537770 | 213.572218 | .000615935 | 384 | 5.448 |
| 053 / 0 / shared | 9419.602988 | 9187.066407 | 232.536581 | .000124227 | 354 | 5.080 |
| 053 / 0 / contrast | 9354.341632 | 9123.079927 | 231.261705 | .000056256 | 317 | 5.466 |
| 053 / 1 / shared | 9480.699235 | 9274.553680 | 206.145556 | .000553954 | 336 | 5.413 |
| 053 / 1 / contrast | 9446.129449 | 9221.951033 | 224.178417 | .000292535 | 338 | 5.918 |

No accepted fit exceeds its own feasible initializer objective. Every contrast fit also beats its paired accepted shared training objective, which is a feasible tied-coefficient state. Thus neither reported training bound flags search incompleteness. This does not prove global optimality. More training flexibility alone did not predict transfer: contrast lowers training J on every fold, including the failed predictive A035 fold0.

Source `8775e273c` passed seven owned tests and Ruff, including actual shared/contrast fitter dispatch, diagonal/matrix prior metadata, unchanged fixed positions, grouped masks, failure/no-retry/all-eight barrier and feasible-bound reporting. Source/input authority was frozen before preparation. Actual12-objective/zero-fit qualification completed7.711s, checking full/fold exact nesting, fixed full band fraction, complete raw domain/initializer identity, additive NLL, prior-corrected gradients and common-row posteriors. Actual initializer changes are zero. The upstream454-objective qualifier checks all new coefficients at nonzero contrast; actual physical/timing gradients were checked by tied nesting only. Actual nonzero-contrast physical FD readiness for free localization is not claimed.

Random whole20s block assignment used the existing helper, seed20261014, without redraw. A035 has1512/1395 training windows and fold0 blocks{0,2,4,5,12,14}, fold1{6,7,8,9,10,13}; row-fold SHA256 `d5dc5b8628b23007092f775b1133c7003accb964c96952224c89d90e35fa6f27`. A053 has881/989 windows and fold0{0,1,2,3,12,14}, fold1{5,6,7,9,10,13}; row-fold `cd1388fe67050c84da783bfb13c0c1a2643d3bea6826a62c6683be3e6d6d3230`. Complete masks/maps and both-band support were recorded before fitting.

Exactly8 calls, up to4 single-thread workers in two case waves; each stayed within20s/600 actual target objectives including independent terminal audit. Contrast internally evaluates two band child densities per target call. Whole units9.139–11.916s include preparation/authority checks. All eight outcomes sealed before8 predictive objectives/zero fits in7.559s. No new free-position fit, failed-fit repair, accuracy comparison or prototype promotion is included. The next useful A053 test requires a separate full-data protocol and actual nonzero-contrast physical/timing gradient qualification; A035's negative predictive result remains a control.

Runtime `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-a-band-detectability-cv-v1`. Qualification SHA256 `e7875450f68bd24b116caa939f8863c6cbaad49eda65574c89f8f144a6d6ceea`; scientific seal `122293d6bf9f00c98f760180766786fbed0b1d7076a27c37090583c10d12de74`; postseal predictive evaluation `9003c779846ab88b10b4e2aa66cfada1a0fae144ba60ea4a8641ad954b1aee17`. Original cohort and previous scientific results remain unchanged.
