# C003 boundary release and C023 interior control

The current coverage C003 all-band winner was limited by its winning 25 km disk. A matched continuation from the same saved all-band state, recentered on that state's XY, reduced configured-reference error **5.214916191 → 1.820654503 km**. The C023 interior control returned exactly the same state in both disks, **5.258300227 km**. All four returned fits passed independent objective/NLL/KKT replay with zero delta. This is useful causal evidence for C003's winning local disk, not achievement of the localization target: C003 still trails its current high-band 0.905250945 km and neither case is below 0.5 km.

The frozen protocol is `MODEL_C_DOMAIN_CONTROL_PROTOCOL.md` (implementation aadea74e7); the zero-fit source/geometry protocol is `MODEL_C_DOMAIN_PROTOCOL.md` (d60d1d4c6). Existing scientific sources and baseline histogram inputs were not edited. All calls fit c. No reference, held data or half-view correction was used in seeds or centers.

| Case | Original-repeat objective | Recentered objective | Original-repeat NLL | Recentered NLL | Original-repeat RMS Hz | Recentered RMS Hz |
|---|---:|---:|---:|---:|---:|---:|
| 003 | 27361.454402401054 | 27116.940693830355 | 27169.244151981813 | 26928.217467545575 | 96.372895441 | 88.433888256 |
| 023 | 28547.848275733195 | 28547.848275733195 | 28305.633778946172 | 28305.633778946172 | 109.312357280 | 109.312357280 |

These frequency scores are training diagnostics. No held-frequency evaluation was prepared for this four-call control. Configured-reference errors were joined only after both cases and all four outcomes were sealed; the reference is the existing configured receiver location, not an independently surveyed location established here.

| Case/condition | Independent own-domain KKT | Evaluations | Fitter elapsed s | Error km |
|---|---:|---:|---:|---:|
| 003 original disk | 0.000542248160 | 577 | 20.066546 | 5.214916191 |
| 003 recentered disk | 0.000653233694 | 214 | 8.542814 | 1.820654503 |
| 023 original disk | 0.000984689724 | 21 | 0.447441 | 5.258300227 |
| 023 recentered disk | 0.000984689724 | 21 | 0.440619 | 5.258300227 |

Each call retained the original 20 s / 600 iteration limit. Reported fitter elapsed includes its original post-optimization audit; C003's original-repeat report exceeds 20 s slightly for that reason. The whole four-call slice completed in 52.503452772 s, below its 180/195/200 s internal/TERM/KILL caps, including validation, preparation, source rechecks and sealing. The host concurrently ran five owned prerequisite workers, root DS22 work and unrelated capture/analysis processes. There was no new fit budget or retry. The two calls per case are additional warm controls; upstream discovery/initialization/54-call case costs remain incurred.

C003's saved endpoint was 25.000000000153 km from its winning shape-high center. The original-domain KKT was 0.000680708267, while the same endpoint's recentered-domain KKT was 44.656196848. Its outward derivative was −58.412155337 per km, tangent derivative −0.000047828, and the outward first meter improved objective by 0.049224426. The two feasible signed 1 m disk arcs increased it by about 0.003911. At that outward meter the low-band NLL improved by 0.124285598 and the high-band NLL worsened by 0.075061172. Fixed-nuisance outward 100 m and 1 km increased the objective by 85.945984 and 6627.649824; the useful 4.809341008 km fitted displacement therefore required nuisance/timing reoptimization.

The recentered C003 endpoint is 29.759819509 km from the winning original center and consequently unavailable to that particular original call. It is only 13.340619389 km from the existing cold-0 center `[-75,-75]`, so the union of all original search disks did not exclude it. The experiment identifies a winning-disk/path interaction, not proof that every original start was physically prevented from reaching the improved mode or that recentering repairs likelihood bias in general.

C023's saved endpoint was interior, 11.820665750 km from its original center; original and recentered KKT were both 0.000986545066. All sampled fixed-nuisance inward/outward/arc/high-directed probes increased the objective. Its matched fit states and scores are bit-identical. Both actual source endpoints had zero solver-initializer delta; endpoint feasibility was never confused with the solver's optional tiny timing-face initialization margin.

Both original zero-fit audits replayed the saved full objective/NLL exactly and checked that original low/high row-restricted NLLs summed to the full NLL at every probe, preserving full-frame nuisance and candidate priors. Each audit used 17 original objective calls and zero optimizers: C003 12.607088310 s including 11.842908681 s preparation/validation; C023 11.216251401 s including 10.509914176 s preparation/validation. Eleven audit/component tests and five control tests passed; owned Ruff checks passed.

Receipts under `local/`, SHA-256:

| Receipt | SHA-256 |
|---|---|
| `model-c-domain-003-v1/result.json` | `841e4127d4adac4a00c21d298a50064ec947074a173e892629df0e0e4582f93e` |
| `model-c-domain-023-v1/result.json` | `4a706316179fcb82473240d1d5c2277c66ca4ec8b3d62aad46ad1037a23de64a` |
| `model-c-domain-control-v1/protocol.json` | `649a1138e59b31ea3e4d0eb1a9f8ef7689bd32ae184819577a8f44989dfd2cd6` |
| `model-c-domain-control-v1/terminal.json` | `e1303350a61028e8d5159003d1aa9e973475e89b713972922a3916b9d3dd9e0c` |
| `model-c-domain-control-v1/seal.json` | `d03bf5d6101263d2030e11a4c0b27936084a2b40ac60ff3544ce5d5d83559b07` |
| `model-c-domain-control-v1/termination.json` | `373b1ff2de1284e0b5b4f2db06a918a28f16c25c456719d32a35dd118c8e3b05` |
| `model-c-domain-control-v1/development-errors.json` | `46208c25d9469be00490d14ce66af738a716cb88adf3fce5aa62349f33a7410d` |
