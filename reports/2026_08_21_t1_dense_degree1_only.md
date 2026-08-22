# Strict degree-1 T1 candidate association

Capture: `cap-20260821T201522-841b2a20e151`
Path: `stream-0/RX1`

## Result

The independently searched raw-IQ candidate inventory supports four straight frequency epochs separated by downward frequency steps. No order-2 or order-3 radio model, published final-trajectory membership, neighboring-probe seed, or TLE prediction is used. Candidate association is RANSAC followed by Huber straight-line refitting, with at most one candidate retained per probe.

![Strict degree-1 T1 association](figures/2026_08_21_t1_dense_degree1_only/t1-dense-degree1-only.png)

| Piece | Candidate-selected interval | Constant Doppler rate | Step entering | Supported probes | Median absolute residual |
|---:|---:|---:|---:|---:|---:|
| 1 | 0.000–6.825 s | -4954.6 Hz/s | — | 142/162 | 71.7 Hz |
| 2 | 6.825–13.525 s | -5560.5 Hz/s | -4.98 kHz | 235/237 | 97.9 Hz |
| 3 | 13.525–20.250 s | -6175.2 Hz/s | -4.25 kHz | 260/261 | 23.5 Hz |
| 4 | 20.250–27.250 s | -5886.1 Hz/s | -4.65 kHz | 251/262 | 39.8 Hz |

The first transition is selected at **6.825 s**, not at the earlier plot's ≈7.9 s quarter boundary. That earlier boundary divided the retained trajectory into four equal-duration audit regions; it was not a fitted changepoint. The dense independent candidates instead show the first approximately 5 kHz downward frequency step around 6.8 s, followed by another straight epoch.

None of the three transition times is inherited from a published polynomial trajectory. Four seed windows were placed post hoc away from the visually suspected transitions; straight lines were fitted there, and each transition time was then chosen by maximum one-line-per-side support in its disclosed transition window. The four-piece count and those windows are therefore exploratory choices, not pre-registered changepoint detections.

## What candidate retention and the finer CFO search change

An acquisition basin is one local timing/CFO maximum for one independently searched 20 ms probe. Retaining 32 rather than eight does not create more time samples and does not make probes dependent. It gives the association stage more alternate synchronization hypotheses to choose from after every probe has been scored independently.

![Basin impact around the first transition](figures/2026_08_21_t1_dense_degree1_only/t1-basin-impact-degree1-only.png)

With the dense inventory, the four straight epochs support **888** evidence-bearing probes. At the previously suspicious 7.5–7.9 s endpoint, the controlled hyperparameter ablation recovered 16/16 probes within 500 Hz with 32 basins, versus 12/16 with the persisted eight-basin search. That first comparison bundled several candidate-retention choices and used a locally refitted line. A later fixed-reference one-factor rerun found 15/16 for a finer coarse grid, 14/16 for 32 basins with the original broad separation, and 16/16 when only CFO/epoch nonmaximum-suppression separation was narrowed. Candidate-retention geometry—especially separation policy—is therefore the best-supported local mechanism; count alone is not sufficient. See the [full parameter study](2026_08_22_t1_glrt_search_parameter_study.md).

This changes the earlier conclusion: the apparent loss at the end of the first plotted region is not evidence that the RF line vanished. The line is present in independent raw-IQ searches. What was brittle was which ambiguity basin survived candidate truncation and later association. It does **not** prove that every selected point is Starlink or that the four epochs belong to one spacecraft.

## Look-elsewhere control

![Time-permutation null](figures/2026_08_21_t1_dense_degree1_only/t1-degree1-time-permutation-null.png)

The recorded ordering has 888 supported probes. Across 80 controls that permute complete 32-basin inventories among probe times and rerun all four straight-line searches, the largest null support is 48; the empirical one-sided p-value is 0.0123. This control preserves candidate counts, ranks, CFO and score distributions while breaking temporal coherence. It covers the per-epoch line search but not the earlier human choice to inspect this capture or the transition-window placement, so it is evidence of line coherence—not a satellite-identification p-value.

## Raw scan versus replay

These orange points are from the **dense first scan of raw IQ**, not from replay. The published replay points are intentionally absent: their membership was seed-preserving from a representative selected from a mixed-order family, so reusing them would not be a strict degree-1 rerun. A valid replay comparison must start from these degree-1 associations, dechirp each epoch with its own straight line, and rerun the held-out pilot/control score on the same IQ probes. Until that bounded replay exists, the strongest defensible result is the independent raw-IQ candidate association shown here.

## Reproduction and limitations

- Tool: `tools/report_t1_dense_degree1_only.py`
- Machine-readable summary: `figures/2026_08_21_t1_dense_degree1_only/t1-dense-degree1-summary.json`
- Input candidate inventory: `figures/2026_08_21_dense_independent_glrt/dense-independent-glrt-candidates.jsonl.gz`
- Candidate-only; no payload decoded and no new RF collected.
- The 0.05 margin and 750 Hz residual gates were fixed for this audit but are not a corpus-calibrated detection threshold.
- Thirty-two alternatives increase the comparison count. The matched time-permutation control is therefore essential, and wrong-code/wrong-edge controls remain required before attribution.
