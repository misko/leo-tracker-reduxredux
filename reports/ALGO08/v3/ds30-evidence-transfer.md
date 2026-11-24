# Signed short-aperture evidence across four DS30 outcome contrasts

The DS30-0049 evidence-loss pattern did not rank the other captures by geographic error. **DS30-0170 improved by 867 m at fixed zero and 620 m fitted**, even though it had a higher rate of installed positives lost or shifted, higher matched-carrier CFO disagreement, and more candidate claims on installed-empty lanes than either regressing capture DS30-0452 or DS30-0124. The separately reserved DS30-0105 also breaks the ranking. These comparisons use previously published positions and signed detections. [Frozen contrast and prospective protocol](ds30-evidence-transfer-protocol.md) · [Sealed per-radio and per-arm receipt](measurements/ds30-evidence-transfer.json.gz)

## Mechanism contrasts selected after the outcomes

| Case | Candidate − installed horizontal error, fixed / fitted | Excess squared error, fixed / fitted | Installed short positives empty or shifted | Strict-match short CFO RMS | Candidate short owners on installed-empty lanes |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS30-0049 | +2.646 / +2.620 km | +16.665 / +14.306 km² | 176/460, 38.26% | 114.38 Hz | 10/225, 4.44% |
| DS30-0452 | +1.506 / +1.576 km | +3.407 / +3.528 km² | 1,407/5,250, 26.80% | 100.81 Hz | 103/3,299, 3.12% |
| DS30-0124 | +0.879 / +0.861 km | +2.783 / +2.712 km² | 1,557/6,055, 25.71% | 96.40 Hz | 98/3,102, 3.16% |
| DS30-0170 | −0.867 / −0.620 km | −0.906 / −0.584 km² | 1,035/3,251, 31.84% | 107.42 Hz | 69/1,504, 4.59% |

Both loss-or-shift rate and strict-match CFO RMS place improving 0170 second highest. The candidate's installed-empty ownership fraction places it highest. Whole-publication owner counts, installed → candidate in either arm, were 320 → 268, 3,989 → 3,822, 4,229 → 3,584, and 2,494 → 1,755, respectively. The improving capture had the largest proportional owner loss, 29.6%. DS30-0049's severe RX1 owner concentration remains a specific observation. Receiver-level installed ownership identities are unavailable on the other captures, preventing a direct transfer test of that pattern.

## Signed lane comparison

The original 20 ms and unfiltered 20/8 ms packets share signed capture authority, ordered stereo opportunities, radio and actual RF, hardware clocks, exclusions, and the offered region. The captured issued/admitted counts were 986/932, 6,773/6,771, 6,772/6,728, 6,769/5,336, and 4,815/4,810 for the cases in table order. The strict carrier signature uses at most 250 Hz of original signed CFO difference and at most two samples of epoch difference modulo the 40,000/3-sample pilot period. `Shifted` means both are positive and the absolute signed difference exceeds 250 Hz. `Empty` means the installed winner lacked a candidate positive on that lane. The strict-match RMS columns measure paired disagreement conditional on that match, and both receivers share part of the input samples. RX0 and RX1 are the native receiver identifiers.

| Case | RX | Short lanes | Installed / candidate positives | Candidate empty | Shifted | Strict matches / both positive | Match CFO RMS | Match epoch RMS | Sparse-only positives |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0049 | RX0 | 811 | 326 / 374 | 30 | 59 | 237/296 | 113.11 Hz | 0.521 samples | 78 |
| 0049 | RX1 | 811 | 134 / 143 | 74 | 13 | 47/60 | 120.58 Hz | 0.401 samples | 83 |
| 0049 | Both | 1,622 | 460 / 517 | 104 | 72 | 284/356 | 114.38 Hz | 0.503 samples | 161 |
| 0452 | RX0 | 5,923 | 3,184 / 3,444 | 283 | 479 | 2,422/2,901 | 98.69 Hz | 0.536 samples | 543 |
| 0452 | RX1 | 5,923 | 2,066 / 2,253 | 390 | 255 | 1,421/1,676 | 104.31 Hz | 0.486 samples | 577 |
| 0452 | Both | 11,846 | 5,250 / 5,697 | 673 | 734 | 3,843/4,577 | 100.81 Hz | 0.518 samples | 1,120 |
| 0124 | RX0 | 5,885 | 3,330 / 3,571 | 298 | 484 | 2,548/3,032 | 95.39 Hz | 0.499 samples | 539 |
| 0124 | RX1 | 5,885 | 2,725 / 2,906 | 411 | 364 | 1,950/2,314 | 97.71 Hz | 0.479 samples | 592 |
| 0124 | Both | 11,770 | 6,055 / 6,477 | 709 | 848 | 4,498/5,346 | 96.40 Hz | 0.490 samples | 1,131 |
| 0170 | RX0 | 4,665 | 1,952 / 2,167 | 259 | 299 | 1,392/1,693 | 104.10 Hz | 0.524 samples | 474 |
| 0170 | RX1 | 4,665 | 1,299 / 1,495 | 293 | 184 | 822/1,006 | 112.83 Hz | 0.509 samples | 489 |
| 0170 | Both | 9,330 | 3,251 / 3,662 | 552 | 483 | 2,214/2,699 | 107.42 Hz | 0.519 samples | 963 |
| 0105 | RX0 | 4,203 | 2,070 / 2,235 | 237 | 316 | 1,517/1,833 | 106.76 Hz | 0.660 samples | 402 |
| 0105 | RX1 | 4,203 | 1,346 / 1,530 | 237 | 170 | 939/1,109 | 95.57 Hz | 0.546 samples | 421 |
| 0105 | Both | 8,406 | 3,416 / 3,765 | 474 | 486 | 2,456/2,942 | 102.63 Hz | 0.619 samples | 823 |

Two 0170 RX0 pairs fail only the epoch test. There are no other short epoch-only failures. The full-anchor matched counts were 71, 718, 821, 427, and 460, all with zero paired CFO RMS. The full-anchor rows still have 0, 23, 31, 17, and 19 signed-shifted winners, and 12, 99, 92, 79, and 70 candidate-only positives. This separates the short-aperture comparison from differences in receiver winner selection that can also affect full anchors.

## Published owner claims and evidence losses

All successor maps reproduce both arms' published observation-to-satellite digests and absolute owner counts. Each count below is the same in the fixed-zero and fitted arms. `Installed empty` means the successor owned a lane where installed's detector had no positive winner. Installed owner-map coverage is exactly 1/5, from 0049's prior official-parity saved diagonal. Coverage on the other installed publications is limited to arm totals and digests. Installed-owned misses, reassignment, and true overlap remain unavailable for those cases.

| Case | Candidate short owner denoms, RX0 / RX1 | Installed empty claims, RX0 / RX1 | Shifted candidate claims, RX0 / RX1 | Same-carrier candidate claims, RX0 / RX1 |
| --- | ---: | ---: | ---: | ---: |
| 0049 | 216 / 9 | 9 / 1 | 30 / 2 | 177 / 6 |
| 0452 | 2,123 / 1,176 | 67 / 36 | 208 / 120 | 1,848 / 1,020 |
| 0124 | 1,807 / 1,295 | 59 / 39 | 137 / 132 | 1,611 / 1,124 |
| 0170 | 953 / 551 | 48 / 21 | 100 / 68 | 803 / 462 |
| 0105 | 1,238 / 868 | 29 / 49 | 133 / 78 | 1,076 / 741 |

On 0049, 44 of 277 installed short owners became candidate empty, with 23/244 on RX0 and 21/33 on RX1. There were 48 installed short owners with shifted candidate winners, 43 on RX0 and five on RX1. Among them the successor abandoned 21 claims, 18 on RX0 and three on RX1. The other 27 shifted lanes retained their assigned satellite and role. The same-carrier group lost two of 185 installed short owners, one per radio. In total, 210 short owners stayed on their original satellite and role in each arm. This makes 0049's concern about loss of measured coverage more specific than a raw count of shifts or surplus positives.

## Prospective DS30-0105

When the first measurement snapshot was frozen, 0105, 0244 and 0183 lacked a complete signed pair. 0105 had an installed receipt only. Once 0105's official pair sealed, it was selected at the first frozen rank without reading any candidate position at enrollment. Its packet metrics froze before independently scoring both original positions. The candidate regressed **483 m fixed-zero and 316 m fitted**. Fixed-zero error was 0.718 → 1.201 km, and fitted error was 0.822 → 1.138 km. Its shorter-aperture markers were intermediate at 960/3,416, or 28.10%, lost or shifted, 102.63 Hz strict-match CFO RMS, and 78/2,106, or 3.70%, candidate claims on installed-empty lanes. The installed and candidate publications have 2,549 and 2,447 owners in each arm. Its narrower geographic regression than 0452 or 0124 coexists with worse markers in all three dimensions. The prospective result remains separate from the previously observed contrasts.

The initial freeze was `af31ba33f`. Before generating signatures, `b6fccb2c0` reconciled the signed 0452 relocation generation and attempt paths. The final reducer at `be100a0f5` authenticated both original 0452 attempts from its separately pinned relocation proof. The pending prospective snapshot digest was `9c70c5651fe9162736ab10e97c81732c009e1984c85fb386665ccbbe5eb7fb65`. The completed packet freeze is `a78497fae830da89f61bdb66a6703e0ed8978325109ce0a98cc90ceb1b4b9947`. The independent score is `18297c4818aff910a28e4264a0452403e35cbddd5d2e3a7039d0ebdadf666eef` and the compressed receipt is `e35d827153e3fc3adc70d87eb8830a484e998921f7bfb47156ea81b02383ef1e`. The readout used saved JSON and no benchmark lease, with zero waveform, TLE, receiver, association, or solver work. Thirteen component and adjacent tests passed. [Read-only reducer](ds30_evidence_transfer.py) · [Component tests](../../../tests/pipeline_eval/test_ds30_evidence_transfer.py)
