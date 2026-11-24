# Candidate-only 8 ms verifier margin predicts held frequency disagreement

A single inverse-margin variance law, calibrated on DS30-0016 and DS30-0049, improved the held same-carrier Gaussian score on all three independent physical recordings. Their lowest- to highest-margin quartiles dropped from **126–130 Hz to 73–88 Hz** RMS difference against the 20 ms receiver. Within-stream discrimination of dual-positive carrier disagreement reached **0.769–0.786 AUROC**. These results qualify the empirical variance gate. They supply weaker evidence for a hard reject or retry and do not measure a position change. [Frozen protocol](held-native-precision-protocol.md) · [Receipts with all counts and clocks](measurements/held-native-precision.json.gz)

| Sustained recording | Short opportunities | Installed-only positive | Sparse-only positive | Both positive, same atom / disagreement | Ceiling on matching installed positives |
|---|---:|---:|---:|---:|---:|
| DS30-0019 | 10,452 | 595 | 900 | 2,888 / 554 | 71.54% |
| DS30-0274 | 11,830 | 939 | 927 | 3,954 / 824 | 69.16% |
| DS30-0220 | 8,704 | 790 | 734 | 1,892 / 534 | 58.83% |
| Total | 30,986 | 2,324 | 2,561 | 8,734 / 1,912 | 67.34% |

Both complete native packets in each pair record the same raw authority, original offer, hardware counters, delivery clocks, admitted opportunities and exclusions. The sparse packet is the authenticated unfiltered 20/8 parent with no remeasurement. The comparison uses the strongest passed factor per radio opportunity and the prior signed 250 Hz and two-sample cut. Of 1,912 held disagreements, 1,911 break the frequency cut. The relaxed alias and epoch-wrap check recovers one additional DS30-0220 match. None of the 2,324 installed-only lanes has a candidate score. Even a perfect classifier of candidate positives preserves only the current 58.83–71.54% same-atom overlap with the stock-positive roster. This is a reference detection ceiling, since either recipe may miss or select a genuine carrier. [Prior signed matching rule](signed-cfo-time.md)

## Conditional precision transfer

The score is proportional to the inverse native fractional verifier margin and the inverse square of the declared 8 or 20 ms aperture. Training on the 529 development short matches gave a relative variance scale of 22,606.4 Hz² and a constant comparator of 13,352.7 Hz². Both scales transfer unchanged. The empirical result concerns variation among short lanes, where aperture is fixed. Matches on scheduled full anchors provide a shared-input control. Their 558, 777 and 444 strict same-atom factors are all byte-identical to their corresponding full factor. Those zeros cannot identify 20 ms variance or test the aperture exponent. The ABI carries one exact and one rolled verifier score, one peak epoch, CFO, margin and pass flag. It has no logged neighboring spectrum points or local peak curvature. [12 ms margin variance experiment](short-margin-variance.md) · [Archived short-peak shape experiment](peak-shape-retry.md)

| Held recording | Same-atom RMS from lowest to highest margin quartile (Hz) | Normalized RMS | Within nominal 95% band | Gaussian loss improvement, nats per match (block 95% interval) |
|---|---:|---:|---:|---:|
| DS30-0019 | 127.9 / 117.2 / 97.7 / 78.0 | 1.033 | 94.74% | +0.0366 [0.0218, 0.0542] |
| DS30-0274 | 126.5 / 105.1 / 84.5 / 72.8 | 1.016 | 95.25% | +0.0634 [0.0520, 0.0757] |
| DS30-0220 | 130.1 / 118.0 / 108.5 / 88.3 | 0.996 | 96.35% | +0.0190 [0.0110, 0.0271] |

The normalization and loss are conditional on the same-atom label. The pairings share original samples, the match cut truncates the error distribution, and the two receiver recipes can share noise or a Doppler-model error. The fitted numbers are a measure of paired disagreement rather than an absolute per-lane CFO uncertainty. Bootstrap intervals resample thirty 10-second hardware-time blocks per case, keeping both radios in the same block. Each held recording passes separately. No owner-based enrollment or position value entered the model.

## Hard classification and coverage

The development specificity rule flags short margins at or below **0.130068**. It retains 95.08% of matching development detections. Its held specificity beats equal-exposure random selection markedly, while its disagreement capture differs by case. Random selection matches the actual flagged count within each receiver/edge/channel/actual-RF stream and can spend budget on sparse-only lanes. Counts in parentheses are the exact random-selection mean and SD with these observations held fixed.

| Held recording | Flagged total | Matching specificity (random) | Disagreements flagged (random) | Within-stream AUROC | Sparse-only among flagged |
|---|---:|---:|---:|---:|---:|
| DS30-0019 | 955 | 97.61% (79.82%) | 120/554 (114.5 ± 8.5) | 0.777 | 766 |
| DS30-0274 | 1,006 | 98.43% (82.72%) | 192/824 (144.6 ± 9.9) | 0.769 | 752 |
| DS30-0220 | 861 | 96.88% (76.72%) | 178/534 (131.9 ± 8.6) | 0.786 | 624 |

The fixed threshold leaves 67–78% of dual-positive disagreements unflagged while 76% of all flags are sparse-only. Their carrier status remains unresolved. The flags capture only 2.95–4.73% of the squared errors among same-atom matches. Equal-exposure random selection captures an expected 17.53–23.37% by flagging many more matching detections. This tradeoff favors evaluating continuous precision without removing rows. It supplies little basis for a general carrier veto or a selective CFO retry budget.

The readout used saved JSON only. The protocol and implementation were sealed at `f5ba2e4f0` and `8ae94bf7a` before reading the held outcomes. The expanded receipt SHA-256 is `5b6b393ad461a71096c655a104c10f7c5db82680768a925d7126fe76836d1162`. Four focused tests passed. Run `held_native_precision.py FRESH_RESULT.json` with read access to the existing authoritative packet roots. [Source and controls](held_native_precision.py) · [Tests](../../../tests/pipeline_eval/test_held_native_precision.py)
