# DS22-019 and DS22-053: original endpoint acceptance and band scores

This zero-fit audit evaluates all six original full-band B/C endpoints, including rejected ones, and each model's training-selected own-half endpoints. It reads saved A stage diagnostics. It does not use a reference, held prediction, new seeds or relaxed acceptance. Half states remain in their genuine own frames; no nuisance vector is transplanted between frames.

| Case/model | Full stationary / six | Low / six | High / six | Selected full disk radius (km) | Accepted full runner-up objective gap |
| --- | ---: | ---: | ---: | ---: | ---: |
| 019 B | 5/6 | 6/6 | 6/6 | 8.546181 | 264.156614 |
| 019 C | 6/6 | 6/6 | 6/6 | 13.111019 | 1101.002103 |
| 053 B | 5/6 | 6/6 | 6/6 | 18.331959 | 379.861026 |
| 053 C | 2/6 | 6/6 | 6/6 | 16.542514 | 1002.474026 |

All eighteen saved A stages (low, high, final across six starts) are stationary on each case. Their final training selection is start 4 on 019 (objective 43122.880450) and start 2 on 053 (47017.102748). No A refitting was done. The full selected B/C states are interior to their original 25-km disks, although other endpoints can lie at the boundary.

DS22-053 B has a concrete acceptance/search limitation: rejected start 5 has objective 43852.108913, lower than the selected 44417.351026. Its KKT residual is 0.002084660 at the 25-km boundary, so it remains ineligible. Relative to the selected state, its low-band NLL improves by 195.059343, high-band NLL by 287.177920, and prior by 83.004850, summing to objective improvement 565.242113. This motivates a separate bounded endpoint-start experiment; it does not authorize replacing the original result or relaxing the threshold. On 019 B, the rejected start is worse than the accepted winner. No rejected C053 endpoint has a lower saved objective than its accepted winner.

| Case/model | Selected full low NLL | Own-low selected NLL | Selected full high NLL | Own-high selected NLL | Full prior |
| --- | ---: | ---: | ---: | ---: | ---: |
| 019 B | 23778.101112 | 24011.364903 | 16558.114969 | 16401.160594 | 600.383162 |
| 019 C | 24053.040949 | 24033.309217 | 17228.438145 | 16502.576101 | 391.871502 |
| 053 B | 22418.811072 | 22782.650753 | 21353.690621 | 21051.406449 | 644.849332 |
| 053 C | 23009.742827 | 23113.281266 | 22182.107156 | 21451.148414 | 421.327298 |

The C high-band deficits are 725.862044 on 019 and 730.958741 on 053. C019 low-band likelihood is close to its own-low state (+19.731731); C053 full actually has lower low-band NLL than its own-low state (−103.538439). The DS22-001 low-band sacrifice is therefore not a universal failure pattern. Scores from differently sized observation sets or different priors are not ranked against each other: the table compares only the same band's data contribution, while showing the full prior separately. Better likelihood alone does not establish better position accuracy.

Source `c6815692b` passed fifteen tests and Ruff, including endpoint eligibility preservation and exact B/native likelihood accounting. Original source/ancestry and all sealed endpoints were bound before execution. Both cases completed within their independent 120-second cap: 019 took 33.563 seconds and 053 took 38.821 seconds, each with sixteen objective evaluations and zero fits. All saved objective/NLL values and band sums replayed. The B summarizer emitted empty-opposite-band mean warnings for own-half models; those empty groups were excluded from persisted results, and JSON serialization rejected any nonfinite value.

Complete endpoint inventories, including A stages, and all per-state band contributions are under `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-worst-band-audit-v1/DS22-019/report.json` (SHA-256 `6336e0239bd123564d08ce0abc3e3b030d2f4e1180f890df13a4493397e906ad`) and `DS22-053/report.json` (`3eca6a9bcd99d7c6182cf286e577cf19f316679caee96ed9d8d09da27f85facd`).
