# A053 smooth-horizon matrix: all accepted, full remains 1.148 km

All 27 prespecified calls pass strict acceptance. Across the three fixed widths, the full selector remains approximately **1.148 km**, essentially the same as the current hard-model full baseline 1.148233 km. The middle and widest widths select both conditional halves below 1 km, leaving their full result worse than both. No width is selected by accuracy, no model is promoted, and the full-position target remains unmet.

| Sine-elevation half-width | View | Training-selected complete source | Own J | Frequency NLL | Strict KKT | Configured distance km |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| 5e−6 | Full | Full | 19299.943272 | 19020.770174 | 0.000406655 | 1.148252 |
| 5e−6 | Low | High | 12854.212305 | 12706.274613 | 0.000082266 | 0.630473 |
| 5e−6 | High | High | 6142.299734 | 5966.148355 | 0.000136174 | 1.444907 |
| 1e−5 | Full | Full | 19299.943279 | 19020.769644 | 0.000062751 | 1.148260 |
| 1e−5 | Low | High | 12741.246449 | 12596.914239 | 0.000975079 | 0.656590 |
| 1e−5 | High | Low | 6132.279720 | 5965.652798 | 0.000354358 | 0.701089 |
| 2e−5 | Full | Full | 19299.943305 | 19020.768630 | 0.000219345 | 1.148273 |
| 2e−5 | Low | High | 12690.039462 | 12550.262914 | 0.000378580 | 0.860641 |
| 2e−5 | High | Low | 5958.440960 | 5801.634018 | 0.000166403 | 0.928054 |

Low/high are conditional masks of the full-derived model, retaining its candidate bank, frame, fixed learned receiver shifts and original 50 km disk. They are not independently trained/discovered half-only A pipelines. The 3 × 3 × 3 matrix uses exactly the same three current training-selected complete source states for every view and width; all physical, timing, clock and q state is retained at initialization.

The current hard-model full/low/high errors are 1.148233/1.659857/1.444907 km, with own frequency NLL 19020.777883/12603.761207/5966.148355. Frequency-fit and prior effects must be separated from position: the narrowest smooth low selector has **worse** frequency NLL by 102.513406 despite lower J, because its prior drops by 119.765338. The middle and widest low NLLs improve by 6.846968 and 53.498293; their priors also fall. Full NLL changes by less than 0.01 while its position is essentially unchanged. These are descriptive comparisons between explicitly different densities, not cross-model MAP selection.

The low winners all originate from the complete high state; the middle/widest high winners originate from the complete low state. Thus the half improvements cannot be attributed exclusively to smoothing: these cross-view complete-state starts were not all present in the earlier hard controls. A matched unchanged-hard-model 3-view × 3-state control (nine calls) is the direct next discriminator. The current experiment does not compare equal cumulative search budgets with historical results.

Before any fit, all three original hard own-view incumbents replayed and all 27 soft model/state combinations passed source/initializer/domain qualification (30 objectives, zero fits, 7.141 s). The old low/high states independently satisfy each soft model's strict KKT and remain eligible fallback states. The hard full state does not satisfy soft KKT and was explicitly excluded until newly fitted; no eligibility was grandfathered. Each selector considers all accepted new states and every eligible requalified source state under its own objective. No location reference selected starts, widths, candidates, disks or winners.

Every new call retained 20 seconds/600 **actual** objective evaluations including final replay, through an explicit counted soft port. A regression catches accidental hard-model reconstruction. All 27 calls complete, with 8201 actual optimization objective evaluations total and maximum numerical time 8.965 s. Six single-thread workers completed the wave in 65.511 s. Independent returned-endpoint audits add 27 objective evaluations. No failure was retried or acceptance threshold relaxed. Four driver tests plus eight model/qualification tests and Ruff pass.

Source `d00f07a6f`, model `496078a1b`; actual derivative qualification is reported separately in `model_a_smooth_visibility_qualification_results.md`. Actual all-coordinate FD was at width 1e−5; other widths received actual score/partition and all 27 initializer checks, plus shared-formula component tests. Width is numerical regularization, not a fitted physical detection uncertainty.

Namespace `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-a053-smooth-visibility-control-v1`; operational wave `model-a053-smooth-control-wave-v1`. Global scientific seal `c554054be6034f6ec3e706d03b5d509f1583c6c0e3f5fc95e247f3d2fea170f7` binds all 27 outcomes and nine selectors before reference evaluation. Post-seal evaluation used zero objectives and 6.771 s. Evaluation SHA256 `08eaa32833064959e41d5bbc479de2647d4e30a90b7a8e84cff5f2cc5a2ec545`. No held observations or new RF data were used. All old science and the v1 freeze-only arithmetic defect remain preserved.
