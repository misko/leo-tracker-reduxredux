# Signed CFO calibration from shared pilots

Eight development recordings provided 28,001 literal gated-winner pairs from authenticated complete four-region and original detector factors. The frozen correction adds **−0.736 Hz** to the signed tracking CFO of each fast gate-positive candidate. The six held recordings were selected by physical edge and capture-manifest hash before model fitting. Original held measurements and survey positions entered scoring after the fast-only prediction plan and positions were sealed. [Cohort lock](cohort-lock.json) · [Model lock](model-lock.json) · [Protocol](PROTOCOL.md)

## Development

The match joins the same recorded visit, receiver, RF, and clock. Gated winners must agree within two wrapped epoch samples and 1 kHz of literal signed CFO. The census retains CFO aliases, a literal gated alternate, a literal rejected candidate, and each side's missing gates. Only literal gated winners train the correction. [Training pairs](training-pairs.jsonl.gz)

| Model | Mean per-recording median absolute signed CFO residual (Hz) |
|---|---:|
| No correction | 18.728 |
| Global median offset, left-out recordings | 18.674 |
| Robust affine signed CFO, left-out recordings | 18.681 |
| Edge and RF median with fallback, left-out recordings | 18.749 |

The affine fit estimated 0.944 Hz per MHz of signed CFO. Edge and RF medians used an edge fallback when development support was sparse. Neither richer model cleared the declared 1 Hz improvement over the global offset. [Per-recording model scores](model-lock.json)

The intervention changes the CFO of admitted fast candidates alone. It preserves every physical window, gate, rank, epoch, score, and rejected candidate. Earlier shared-winner and winner-transplant experiments used held donor measurements to change support or select the original winner. Pilot distillation learned a gate and compared retained families. The orbit-influence experiment perturbed support after association. Here the complete fast stream keeps its candidate roster, and the compact receiver rediscovers tracks under the same release and causal request after a sub-Hz measurement shift. [Shared-winner experiment](../../track-recovery/shared-winners/README.md) · [Winner transplant](../../pilot-influence/winner-transplant/README.md) · [Pilot distillation](../../receiver-deadline/pilot-distillation/README.md) · [Orbit influence](../../redesign/orbit-influence/README.md)

## Held pilot agreement

The six captures contained 40,638 scheduled visits, 40,151 valid visits, and 80,302 physical receiver probes. Fast published 25,471 positive probes from 118,020 passing candidates and 385,550 total candidates. Original published 24,478 positive probes from 71,864 passing candidates and 364,243 total candidates. There were 2,552 fast-only positives, 1,559 original-only positives, and 53,272 probes with neither gate positive. Among the 22,919 double-positive probes, 22,163 were literal winner matches, 86 were aliased winners, and 670 had different winners. The unmatched original winners also had 363 passing literal fast alternates, zero literal rejected counterparts and 33 alias alternates. [Held census](audit.json) · [Literal pairs](held-pairs.jsonl.gz)

| Held edge | Literal pairs | Signed median (Hz), fast → corrected | Absolute median (Hz), fast → corrected | Absolute p95 (Hz), fast → corrected |
|---|---:|---:|---:|---:|
| Lower | 11,437 | −0.302 → +0.434 | 15.856 → 15.850 | 75.463 → 75.192 |
| Upper | 10,726 | −1.207 → −0.471 | 19.052 → 19.100 | 101.201 → 101.386 |
| All | 22,163 | −0.682 → +0.054 | 17.350 → 17.295 | 86.666 → 86.616 |

Sign reversal moved the pooled signed median to −1.417 Hz and the absolute median to 17.379 Hz. The frozen offset centers the pooled signed residual and leaves the typical absolute measurement error near 17 Hz. The two edges start at different median offsets, and the upper absolute median and tail increase slightly under the shared correction. The literal match establishes agreement between the two detectors at the same probe. Satellite identities are discovered downstream. [Residual distributions and sign control](stage.csv) · [Stage figure](stage.pdf)

## Held compact positions

Each cell gives geographic error in meters for zero and fitted calibration, in that order. Both arms use the same detector outputs, search, priors and candidate roster. The standard paired charts include the baseline, selective gap, omitted track one and omitted tracks v5 roles. [Zero-c chart](charts/c0/modifications.pdf) · [Fitted-c chart](charts/fitted_c/modifications.pdf) · [v5 values](v5-controls.csv)

| Edge | Recording | Full fast | Corrected full fast | Full original |
|---|---|---:|---:|---:|
| Lower | DS26-0241 | 820.1 / 872.4 | 811.7 / 870.2 | 599.6 / 685.1 |
| Lower | DS29-0127 | 755.7 / 720.9 | 755.7 / 720.9 | 632.9 / 579.0 |
| Lower | DS29-0357 | 530.0 / 570.5 | 530.0 / 570.5 | 436.2 / 433.9 |
| Upper | DS29-0174 | 792.9 / 805.9 | 763.2 / 778.3 | 886.0 / 917.6 |
| Upper | DS29-0316 | 834.0 / 851.9 | 808.0 / 819.7 | 1,006.0 / 1,010.1 |
| Upper | DS29-0604 | 735.1 / 733.7 | 709.3 / 708.5 | 969.7 / 1,028.6 |

All six full-fast, corrected and full-original endpoints published in both arms. The correction improved four cases by more than 1 m in each arm. The other two moved less than 1 mm. Mean error fell by 15.0 m and 14.5 m, and maximum error fell from 834.0 to 811.7 m and 872.4 to 870.2 m respectively. The count within 5% and within 10% of the v5 baseline stayed at three of six in each arm. Each lower recording still favors the original detector by 94–212 m at zero c and 137–185 m at fitted c. Each upper recording already favored fast. [Scores and tail distributions](audit.json)

On DS29-0174, reversing the sign improved error by 31.0 m at zero c and 28.8 m at fitted c. The learned sign improved those same errors by 29.7 m and 27.6 m. The other predeclared reverse-sign fit, DS26-0241, reached the 210 s wall cap on a shared core after 100.2 CPU s and yielded no position in either arm. The complete sign control therefore covers one recording and gives no directional geographic evidence for the learned CFO offset. [Paired changes](paired.csv) · [Lower control terminal](receipts/DS26-0241/reverse/service.log)

The correction preserved all admitted observations. Normal rediscovery returned one fewer track on DS26-0241, DS29-0174, and DS29-0316. DS29-0316's reported coordinate moved 484 m at zero c and 472 m at fitted c, while the error decreased by 26 m and 32 m. Mean conditional RF RMS decreased 0.180 Hz at zero c and 0.181 Hz at fitted c. The original detector retained a roughly 9 Hz mean conditional RMS advantage. [Compact support and frequency fit](paired.csv) · [Sealed position records](positions.jsonl.gz)

## Cost boundary

The six complete CFO transformations used **1.351 CPU s** in total, 136–322 ms per recording, for 118,020 admitted candidates. This times the in-memory transform. The archived authentic four-region detections used 893.9 CPU s across the same inputs. Per-recording medians of raw detector-call latency ranged from 15.7 to 26.1 ms and p95s from 21.0 to 34.3 ms. The six fresh corrected compact solves used 478.7 CPU s in total and 65.1–119.2 s elapsed per solve. The prior uncorrected compact solves used 413.4 CPU s under different run conditions. Full original acquisition costs on these archival captures are projected. [Separate timing boundaries](costs.csv)
