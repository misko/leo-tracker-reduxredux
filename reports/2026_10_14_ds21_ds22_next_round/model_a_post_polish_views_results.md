# Current A q selectors: conditional channel-view comparison

The updated full/CH1–4/CH5–8 configured errors are **035: 7.223109 / 7.101238 / 7.495502 km** and **053: 1.343357 / unavailable / 1.444907 km**. A035 full remains slightly worse than low. A053 full beats high, but its low-view fit fails strict convergence, so no complete comparison is available. These are full-derived conditional views, not independent half-only A pipelines or a cohort-target result.

The prespecified source is the **PD method's own training-selected common q state** from `model-a-propensity-polish-control-035053-v2`. Both current full selectors differ from the earlier eligible-only q winners. The older 0.256462 km full / 0.190263 km low A053 results remain valid for their explicitly older version and are not mixed into this table. Numerical eligibility repair exposed a lower-objective, less accurate A053 state; it supersedes the earlier sub-kilometer selection headline.

New source `ac9c0b847` consumes the genuine numerical-control parent and reuses the qualified conditional-view math port. Six tests and Ruff pass. Every half starts from the exact current full vector, clock nuisance and q tail, retaining banks 55/59, full-derived RF/time frame and clock nodes, learned high shifts fixed in baseline, fitted-c freedom, priors and original 25/50 km disks. No alias repair, projection, reference seed or held observations are introduced. Upstream use of both bands remains explicit development leakage.

Actual partition qualification passed **six objectives, zero fits**, in 10.461 seconds, verifying each current full-state likelihood and identical half-row posteriors. Four independent original-solver calls use 20 seconds / 600 iterations, four single-thread workers, and 90/105/110 second whole-unit bounds. Wave152 completed in **15.368 seconds**. All four original outcomes sealed before reference scoring: `28e66db89d478ec29fa8551b2f3a2ff844ca4290dd3048993ff8002032441aa1`.

| Case / current view | Conditional NLL | Strict KKT | Radius / own disk km | Configured error km |
|---|---:|---:|---:|---:|
| 035 full PD source | 28571.605383 | 9.96e−8 | 7.207 / 25 | 7.223109 |
| 035 CH1–4 | 16675.368715 | 0.000512811 | 7.196 / 25 | 7.101238 |
| 035 CH5–8 | 11538.395688 | 0.000907523 | 4.232 / 25 | 7.495502 |
| 053 full PD source | 19033.058089 | 2.12e−8 | original 50 km disk | 1.343357 |
| 053 CH1–4 | 12603.704306 | **0.8981289998** | 33.194 / 50 | unavailable |
| 053 CH5–8 | 5966.148355 | 0.000136174 | 33.124 / 50 | 1.444907 |

NLL totals from different row populations are not one ranking. Per-band, receiver and prior ledgers are retained separately in the numeric receipt. Three of four fits pass unchanged independent full-freedom KKT ≤0.001; A053 low remains excluded without retry or threshold relaxation. No older half endpoint substitutes for it. Configured coordinates remain unconfirmed physical truth.

The additional cost is four real calls plus six qualification, four independent endpoint-audit and four post-seal scoring objectives. The ongoing root cause is not solely first-order eligibility: repaired full A053 training selection is less accurate than an eligible older endpoint, and the earlier conditional CV already showed +377.047 opposite-fold q NLL. There is no q cohort promotion. The next authorized cross-model numerical check concerns B059's similarly rejected lower-objective fixed profile; it does not modify these A outcomes.

[Numeric outcomes and exact provenance](model_a_post_polish_views_results.json). Output: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-a-post-polish-half-views-035053-v1`.
