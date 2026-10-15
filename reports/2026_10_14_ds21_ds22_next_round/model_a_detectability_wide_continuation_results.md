# A029 widened-domain fresh continuation: still rejected

One explicitly additional optimizer invocation from the complete rejected widened-domain endpoint did **not** repair eligibility. It returned J **28421.146958107696**, essentially unchanged (−2.66e−10), with independent KKT **0.003188312**, above the unchanged 0.001 gate. It consumed **50 actual objective evaluations in 0.917 s**, including the independent audit, far below 60 s / 6,000 actual / 600-iteration limits. There was no wall-clock, evaluation-budget, or outer-process failure.

The previous widened-domain call remains preserved as a separate failure (J28421.14695810796, KKT0.002076382). The new initialization copied its entire vector and nuisance state, preserving learned contrast, q parameters, clock, timings, fitted c, observations, bank, priors, and domain. No projection, source replacement, threshold relaxation, or automatic retry occurred. This invocation is extra search cost, not part of the previous matched six calls.

The wider local disk continues to cover the full original global 250 km prior, whose constraint remains enforced. Neither rejected endpoint is a wider-domain estimate or eligible incumbent. The accepted original-domain case estimate remains **39.987144 km**. The new outcome and selectors were sealed before the post-seal reference join; no position error was computed for a rejected endpoint. No held data were accessed. A071's separately sealed 0.195307 km contrast result is unchanged.

The early stop at nearly constant J motivates a bounded numerical derivative/ULP/support audit, not another blind SLSQP continuation or an accuracy claim. A local coordinate audit cannot by itself establish a coupled minimum or global model adequacy.

Source `da023504e`; ten owned/current tests and Ruff passed before freeze. New namespace: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-a-detectability-wide-continuation-029-v1`. Unit whole time was 15.672 s under 120/135/140 s bounds. The adjacent JSON binds protocol, terminal and seal and preserves the complete accepted/rejected selector records. Original scientific sources and failures remain immutable.
