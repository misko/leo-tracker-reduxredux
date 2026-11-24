# Empty short lanes remove timing support from installed satellite assignments

On DS30-0049 and DS30-0086, **44 of 104** and **323 of 564** installed full positives on candidate-empty short lanes reached final ALGO08v3 ownership. Removing just those observations from the authenticated installed owner time series cuts **13.8% and 13.0%** of owners, and **23.6% and 15.7%** of the time design for curvature. On the other two held recordings, the installed publications retain only owner totals and digests, so exact missed owners remain unknown. Both calibration arms have the same observation-to-NORAD maps on the two exact cases and the same per-arm owner totals and map digests on the two bounded cases. [Frozen protocol](missed-owner-support-protocol.md) · [Sealed readout](measurements/missed-owner-support.json).

| Recording | Installed positive count | Candidate-empty short lanes | Installed owners among those misses | Strict common short detections | Installed owners among those common detections |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS30-0049, development | 531 | 104 | 44, exact | 284 | 185, exact |
| DS30-0086, held | 3,328 | 564 | 323, exact | 1,880 | 1,545, exact |
| DS30-0019, held | 4,614 | 595 | 0–595 | 2,888 | 1,646–2,888 |
| DS30-0274, held | 6,522 | 939 | 0–939 | 3,954 | 1,850–3,954 |

The installed owner fraction among the misses is **42.3%** on 0049 and **57.3%** on 0086, versus **65.1%** and **82.2%** among strict common shorts. The remaining 60 and 241 misses were installed nonowners. The detector join uses the original signed hardware window, receiver, edge, channel and RF. Strict common requires agreement within 250 signed Hz and two absolute samples without alias rolling. Disagreeing dual positives remain separate, as do full anchors, candidate-only rows and both-empty rows. The receipt accounts for all 36,918 signed lane opportunities across the four cases. The unresolved ownership intervals use the arithmetic bounds from the installed positive count and the published owner count. They permit all or none of the misses to be final owners on 0019 and 0274. [Earlier receiver census](first30-native-agreement.md) · [Original paired CFO study](track-cfo-denoise.md).

## Where the exact missed owners fell in time

Group the installed owners by NORAD and physical lane, splitting the original chronological support at gaps longer than eight seconds. These groups use exact signed observation identities but do not require a fitted role or satellite trajectory. Hold the original groups fixed when comparing time support. The reported duration is the sum of first-to-last intervals over those groups. The slope design removes a group mean from time. The quadratic design removes a group mean and linear trend from squared time. Neither quantity estimates geographic information or credits a surviving detection that would receive a new owner after refitting.

| Removing only installed owners on candidate-empty short lanes | DS30-0049 | DS30-0086 |
| --- | ---: | ---: |
| Original temporal groups with at least one such miss | 8/9 | 46/68 |
| Satellites affected | 2/2 | 22/27 |
| Groups that lose their first / last owner | 4 / 3 | 14 / 17 |
| Newly opened gaps longer than eight seconds | 0 | 1 |
| Pooled group duration before → after | 247.01 → 226.45 s | 1,979.08 → 1,920.25 s |
| Linear / quadratic design lost | 19.1% / 23.6% | 14.9% / 15.7% |
| Missing owners before / between / after strict common owners | 10 / 14 / 14 | 61 / 204 / 58 |
| Missing owners in groups without a strict common owned short | 6 | 0 |

No temporal group vanishes when removing only the empty-lane misses, since other installed support remains in each group. If dual-positive disagreements are also omitted while retaining original full anchors, the quadratic time design loss rises to **46.6%** on 0049 and **29.7%** on 0086, and new long gaps rise to one and three. On 0049, empty losses disproportionately shorten the support at its ends. On 0086, most are inside the common support, but a third still lie outside its first-to-last common interval. A receiver rule tuned only to gaps longer than eight seconds would miss most of these changes. The published results omit the installed Graph piece indices and final fitted orbital aliases. The time calculations therefore describe the authenticated owner observations on native lanes, rather than assigning a missing factor to an inferred Graph piece.

## Nearby candidate detections offer limited discrimination

Having candidate positives within two seconds on **both** sides of the missed window, in the same physical lane, covers **24/44** owned and **30/60** unowned misses on 0049. It covers **231/323** owned and **154/241** unowned misses on 0086. The corresponding coverage for common short detections that have installed owners is **181/185** and **1,460/1,545**. Nearby candidate positives establish measured activity. Their carrier and final ownership need independent confirmation. In particular, 0049 RX0 has 23 owned misses among 30, compared with 21 among 74 on RX1. Both-sided context covers 13/23 and 11/21 of those respective owners, while also covering 4/7 and 26/53 of the nonowners. The frequency of nearby detections alone gives little selectivity for eventual installed ownership.

Earlier studies measured candidate-side time leverage or compared complete owner maps from different packets. This subtraction instead isolates the empty short class inside one exact installed map and compares it with the full-only nonowners. The earlier 0049 empty-lane intervention improved location error by 324/377 m, but using that reported improvement to predict either the present time-mask outcome or another recording's location would require a new fit. DS30-0086's earlier combined restoration changed both missed and disagreeing measurements. No location effect is assigned to its empty-only mask here. [Earlier candidate time design](owner-time-support.md) · [Whole owner path](owner-path-correction.md) · [0049 empty recovery](ds30-0049-empty-recovery.md) · [0086 joint recovery](ds30-0086-joint-recovery.md).

The four pairs use sealed detector and publication metadata only. The 0049 selected-owner replay reproduces the installed native and owner digest. The 0086 saved full-packet crossover reproduces the official observation-to-NORAD digest and count. No Graph, fitted alias, raw or catalogue work ran. Three component and eight adjacent tests passed. [Reducer](missed_owner_support.py).
