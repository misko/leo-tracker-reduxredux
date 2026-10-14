# B059 complete-half continuation: current full selection remains

Both declared half endpoints were replayed and continued under the unchanged full-training propensity target. The selector retains current full **1.129758km**. The low continuation is rejected; the high continuation is accepted at.372796km but loses full-target objective by3146.386152. It cannot be chosen by known position. The matched-view regression all1.129758/low1.035045/high.468524km remains unchanged in its separate sealed result.

Source/protocol `2f159889c` passed three owned tests and Ruff before freeze. Eight objective calls and zero fits in14.914s verified both complete half states plus current full: source-half scores, original domain, prior/NLL additivity, original unchanged full bank/frame/q order and exact source-half posterior/residual/q transport. Original fitter initializer adjustments are zero. Source-half acceptance remains distinct from FREE stationarity on full training.

| Source state before full continuation | Full objective | Full low NLL | Full high NLL | Total prior | Full FREE KKT |
|---|---:|---:|---:|---:|---:|
| current full |28054.858757 |17551.372532 |10164.259526 |339.226699 |.000136635 |
| matched low |30680.343406 |17278.041658 |13087.876264 |314.425483 |733.173666 |
| matched high |31340.902448 |21085.298075 |10005.597437 |250.006936 |135.828713 |

Relative to current full, low improves its own band273.330874 but loses2923.616738 in high; high improves its own band158.662090 but loses3533.925543 in low. These are different complete coupled states, not a clean geographic or q-only contrast. In particular each half's group-offset prior collapses to≈1e-14, versus current full.404903. With only one group observed, its receiver/group column is proportional to the receiver intercept, so a group offset can be absorbed into that intercept while changing the unobserved group's correction. The half fit therefore does not identify its correction on the unobserved group; this does not demonstrate hardware calibration error.

Exactly two full FREE calls ran LOW then HIGH from their unchanged complete half states, retaining the original donor25km disk, all original priors/fitted c, q vector/basis/budget/bounds, sigma125Hz and full metadata. Neither non-geographic state nor q was reset. Every call retained20s/600; both outcomes were preserved and sealed before reference joins. Whole optimizer slice23.883s, internal120/TERM135/KILL140 including guards/preparation/audits. Original held/locked measurements were never read.

| Full-target endpoint | Accepted | Objective | NLL | Development error km | KKT | Fit time |
|---|---|---:|---:|---:|---:|---:|
| current full **selected** |true |28054.858757 |27715.632058 |1.129758 |.000136635 |historical |
| low-source continuation |false |30494.534293 |30190.621310 |1.678071 |.440623941 |4.920s |
| high-source continuation |true |31201.244909 |30949.581264 |.372796 |.000172015 |3.338s |

Low reported solver success but fails the unchanged strict KKT≤.001 gate, before its time cap; no retry or tolerance change follows. High is stationary but worse in the same full likelihood by3233.949205, offset only by87.563053 lower priors. Both continuations retain small group-offset priors (3.255e-5/1.593e-5), so another accepted nearby state exists but the transported complete-state basin remains poor. This does not isolate calibration from q/timing effects, exhaust better full-target states, or establish an unavoidable likelihood preference.

The next discriminator is the full calibration basis's ability to represent the low/high fitted correction functions on their own measured rows, using identical native timestamps/RFs and unchanged affine/RF/common-clock/group design. Spliced-function projection residuals, rank/conditioning and coefficients/bounds should be assessed before adding band-specific q freedom. Different source geographies, orbital timing and q remain confounds; representability residuals alone are not hardware-mismatch evidence. No block/channel is dropped, reweighted or chosen by truth.

Output: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-b-half-continuation-059-v1`. Qualification SHA256 `30dfe8ff3294ed28424802e6dfb25ee5653bcbcf7c0a61b69fc6f4c822b4868b`; terminal `1450a79b1358f762641615d0320629f7278b718f5aaaa94c8599dff3973bf5c3`; pre-reference scientific seal `75d8dffc688d0ab829e313f94aa4668ad1414c91b53c2013aa306fb72d3a2edb`; postseal evaluation `cdbf2f5d96a6478b5810c2233a7dc09512ad3fc3facd012fe8e81ca43547018a`. Evaluation took14.284s, zero fits. These two calls add to30 preceding observation-model/control calls plus all upstream work; no standalone two-call accuracy or promotion claim is made.
