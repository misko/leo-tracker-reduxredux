# Full-anchor exposure distinguishes North, but the causal policy fails transfer

Regular 20 ms anchors showed a lower positive rate than the short primaries on North, and the reverse on both physical records. The exposure screen passed for 12 and 8 ms. The frozen past-only policy then discarded **98 of 7,336** positives on dense DS30-0008 and **18 of 456** v3-present opportunities on held South, exceeding the 1% per-radio limits. The experiment stopped before localization. [Exposure protocol](anchor-exposure-protocol.md) · [Frozen policy and transfer gates](past-anchor-policy-protocol.md)

## Exposure census

| Record / primary | Full anchor positives / opportunities | Short positives / opportunities | Short minus anchor, percentage points | 95% interval, 256-visit blocks |
|---|---:|---:|---:|---:|
| North, 12 ms | 82 / 304 | 996 / 2,096 | +20.55 | +13.37 to +29.73 |
| North, 8 ms | 82 / 304 | 1,513 / 2,096 | +45.21 | +39.06 to +53.97 |
| Weak DS30-0016, 12 ms | 74 / 186 | 401 / 1,240 | −7.45 | −10.79 to −2.59 |
| Weak DS30-0016, 8 ms | 74 / 186 | 432 / 1,240 | −4.95 | −8.80 to +0.48 |
| Dense DS30-0008, 12 ms | 956 / 1,696 | 6,380 / 11,834 | −2.46 | −4.66 to −0.35 |

The short-minus-anchor rate was positive on both North radios and all **16 of 16** radio/actual-RF streams at both apertures. Across weak DS30-0016 it was positive in **2 of 16** streams at 12 ms and **6 of 16** at 8 ms, and in **4 of 16** on dense at 12 ms. Both physical radios had a negative pooled rate difference at both measured settings. The 256-visit North-versus-weak contrasts were **+27.99 points [18.89, 37.18]** at 12 ms and **+50.16 [41.37, 59.34]** at 8 ms. North versus dense was **+23.00 [15.31, 32.27]** at 12 ms. The smaller predeclared block width preserved all three contrasts. [Exact by-radio and by-RF counts, rates and intervals](measurements/anchor-exposure.json.gz)

Against the named v3 detector on exactly matched North opportunities, the full anchors added **22 net positives (7.24 points)** and shorts added **600 (28.63 points)** at 12 ms or **1,117 (53.29 points)** at 8 ms. The extra short excess relative to the anchor excess was **21.39 [13.14, 28.75]** and **46.06 [39.14, 52.81]** points at the 256-visit width. The corresponding weak anchor excess was **8.60 points** versus short excess of **1.53 and 4.03 points**. These are pass-rate comparisons of detector outputs. The original full factors were identical between short settings at all anchors on North and weak. [Signed paired reference census](measurements/anchor-exposure.json.gz)

The block resampling keeps chronology and both radios together at site level and preserves the one-in-eight cadence within RF streams. The 128/256-visit resampling has **10/5**, **7/4** and **53/27** original blocks on North, weak and dense, respectively. The intervals characterize those records at two block scales. They carry no estimate of variation between different records at one site, and longer-lived correlation or a systematic phase of the anchor schedule could change their interpretation.

## Frozen causal application

| Record / primary | All positives → kept | Removed where matched v3 passed | First eligible / active / removal issued visits | Hardware seconds to first removal | Audit CPU ms |
|---|---:|---:|---|---:|---:|
| North, 12 ms | 1,078 → 822 | 26 / 456 | 264 / 264 / 264 | 66.000 | 6.15 |
| North, 8 ms | 1,595 → 955 | 32 / 456 | 264 / 264 / 264 | 66.000 | 6.81 |
| Weak DS30-0016, 12 ms | 475 → 475 | 0 / 440 | 256 / — / — | — | 3.08 |
| Weak DS30-0016, 8 ms | 506 → 506 | 0 / 440 | 256 / 384 / — | — | 3.12 |
| Dense DS30-0008, 12 ms | 7,336 → 7,238 | No matched packet in this census | 264 / 390 / 390 | 17.307 | 33.00 |
| Held South, 12 ms | 703 → 654 | 18 / 456 | 264 / 264 / 267 | 66.132 | 5.46 |

The policy left all anchors intact. On North at 12 ms, 230 of the 256 removals were at opportunities where the named v3 receiver published no factor. Dense exceeded its transfer limit on both radios, removing **54/4,156** and **44/3,180** original positives. Held South's full and short counts were **70/304** and **633/2,096**. Its packet bound the same original acquisition, hardware clocks and ordered probe opportunities as v3. The rule removed **3/228** and **15/228** of those v3-present opportunities by radio. No `c = 0` or fitted-`c` position, RMS, decision or solver-cost effect was measured after the failed gate. [Every kept and removed observation ID, arrival counter and cutoff](measurements/past-anchor-policy.json.gz)

First eligibility follows two complete prior 128-issued-visit blocks. Earlier opportunities pass through and the decision on a current lane needs no future arrival. The recorded Python clocks include chronological rule evaluation and materializing the per-factor ID audit. The South candidate came from its genuine saved unfiltered receiver document and was copied as signed JSON to tmpfs. Its containing and far documents have the same hash. The census and application read no waveform, catalogue or bulk payload. Five component tests passed. [Exposure runner](anchor_exposure.py) · [Causal application](past_anchor_policy.py) · [Application tests](../../../tests/pipeline_eval/test_past_anchor_policy.py)
