# Capped full-revisit nominations for missing and disagreeing short detections

The held rule found **399 of 5,063** targets at **2,524** callbacks. The equal-spend periodic rule found **288**. Combined precision rose from **11.4% to 15.8%**, and recall from **5.7% to 7.9%**. All four held captures improved combined hits, but disagreement hits fell from **166 to 103**. The frozen gate required improvement on both classes. Do not advance this rule to a live receiver trial. [Frozen protocol](capped-revisit-protocol.md) · [Development plan](measurements/capped-revisit-development-plan.json.gz) · [Held predictions](measurements/capped-revisit-held-plan.json.gz) · [Held score](measurements/capped-revisit-held-score.json).

The receiver earns one credit per 16 admitted short opportunities independently for each radio, edge, channel and actual RF. It can spend on the current short observation as soon as the credit is available. An empty is eligible when recent same-lane CFO predicts a carrier or the same-visit peer and the recent predecessor are both positive. A positive is eligible when it departs from a signed forecast fitted to the three preceding positives. Existing full anchors update history and incur no retry. The oldest admissible history is eight seconds and the forecast's newest observation must be at most two seconds old. Any unspent credit is used on the final opportunity before the next credit, or stays unused at EOF. A proposed inline integration would make its decision after both short observations become available and while the corresponding signed window is still present. The tested callback path only replays saved metadata.

| Recording | Short lanes | Paid | Missing targets | Missing hits, proposed / periodic | Disagreeing targets | Disagreeing hits, proposed / periodic | Combined hits, proposed / periodic |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| DS30-0049, development | 1,622 | 86 | 104 | 7 / 0 | 72 | 2 / 5 | 9 / 5 |
| DS30-0086, held | 8,372 | 509 | 564 | 65 / 28 | 464 | 24 / 25 | 89 / 53 |
| DS30-0144, held | 11,754 | 727 | 786 | 96 / 43 | 722 | 23 / 56 | 119 / 99 |
| DS30-0170, held | 9,330 | 571 | 552 | 59 / 16 | 485 | 20 / 37 | 79 / 53 |
| DS30-0262, held | 11,590 | 717 | 668 | 76 / 35 | 822 | 36 / 48 | 112 / 83 |
| All held | 41,046 | 2,524 | 2,570 | 296 / 122 | 2,493 | 103 / 166 | 399 / 288 |

Held missing recall was **11.52% vs 4.75%** and disagreement recall was **4.13% vs 6.66%**. Their contributions to precision per paid callback were **11.73% vs 4.83%** and **4.08% vs 6.58%**, respectively. At equal total spend the periodic policy chooses the credit-earning lane for each redeemed credit. A fixed periodic rule that pays on every earning lane would spend 2,538 held callbacks. The difference is 14 unused tail credits. Uniform selection from those same redeemed spans has an expected 313 combined hits on held captures and 10.26 on development. Development's observed nine combined hits are lower than that expectation. [Development score](measurements/capped-revisit-development-score.json).

## The rule allocated most checks to empty lanes

The held method spent **1,992** callbacks on empty short lanes versus **1,353** for periodic. An additional post-seal control picks the first lane in each redeemed span with the same short-positive/empty status as the nominated lane. It uses the realized spend composition retrospectively to measure selection within each class. At that matched allocation, it finds 219 missing and 76 disagreeing targets, versus 296 and 103 for the actual nomination. Thus the forecast identifies more useful positives than that control on its smaller positive budget. Whether separately reserving credits for empty and positive observations retains that advantage remains unmeasured. [Post-seal availability and same-status control](measurements/capped-revisit-joint-score.json).

The original installed receiver emitted any positive on **610/2,524** nominated held lanes and **1,056/2,524** periodic lanes. Of these, **399** and **288** qualify as target replacements. The remaining published installed positives agree with the mixed carrier under the edit definition. A full callback on the original window could return no candidates, a different peak, or more than one peak with a different continuation outcome. No actual nominated full callback or live replacement ran here. The retained original installed factors establish what could be substituted with the answer key. They do not establish a live recovery rate.

## Owner counts and previously realized joint fits

| Recording | Exact installed owner targets | Hits, proposed / periodic | Final owners of edits in archived joint fit | Hits against joint owners, proposed / periodic |
| --- | ---: | ---: | ---: | ---: |
| DS30-0049 | 92 | 4 / 3 | 92 | 4 / 3 |
| DS30-0086 | 634 | 56 / 33 | 672 | 59 / 34 |

These rows agree in both calibration arms. On DS30-0049 the proposed and periodic plans reach one and three of the 66 joint-fit edited owners on RX0, and three and zero of 26 on RX1. On DS30-0086 they reach 21 and 13 of 335 on RX0, and 38 and 21 of 337 on RX1. The joint owners are from earlier saved solves which used every eligible installed edit. These counts are intersections with that realized support. Solving with only the proposed subset could produce different support and positions. The three other held installed publications retain owner totals but omit exact rows. Their provable nominated owner counts span **0–119, 0–79 and 0–112** in case order. The score preserves those intervals, with separate bounds by class and arm. [Original joint fit on 0049](ds30-0049-joint-recovery.md) · [Original joint fit on 0086](ds30-0086-joint-recovery.md).

## Cost and comparison scope

| Recording | Estimated added CPU / wall, s | Actual current wall above half installed, s | With estimated callbacks, s |
| --- | ---: | ---: | ---: |
| DS30-0049 | 0.31 / 0.33 | 4.26 | 4.59 |
| DS30-0086 | 1.70 / 1.81 | 13.20 | 15.01 |
| DS30-0144 | 2.72 / 2.83 | 6.55 | 9.38 |
| DS30-0170 | 1.95 / 2.09 | 10.80 | 12.89 |
| DS30-0262 | 2.92 / 3.06 | 8.20 | 11.26 |

The estimate adds the same recording's mean paid full-anchor callback price and assumes unchanged non-callback work. Live trigger cost and the effect of replacement on solver cost and endpoints are unmeasured. Earlier empty-lane rescue found 89 of 104 development missing factors at 532 calls, with a 1.91 s estimated CPU charge. Earlier supported empty recheck found 11 at 95 calls. The selective positive recheck demonstrated one exact alternate choice on a first member, while its complete DS30-0016 trial was slower and geographically worse. These studies have different nomination and calibration boundaries. The present study adds a jointly capped decision on both target classes and four held comparisons. [Empty rescue](empty-lane-rescue.md) · [Supported empties](empty-short-recheck.md) · [Selective positive recheck](selective-full-recheck.md) · [Complete positive recheck](live-full-recheck.md).

The policy was frozen at `80d03dc13`. Development predictions were sealed at `c314c5f14`. Held predictions were sealed at `171d53cca` before their installed packets or owner maps were opened. Both plans reproduce byte-for-byte. The study used original local signed metadata and the independently checked saved outputs, with no raw reads, solver, timing slot or campaign modification. Five component tests and ten adjacent tests passed. [Reducer](capped_revisit.py) · [Component tests](../../../tests/pipeline_eval/test_capped_revisit.py).
