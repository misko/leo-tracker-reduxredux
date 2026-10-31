# Target-excluded receiver correction diagnostic

All 36 target comparisons still fail the unchanged noise screen. No association, acceptance, production model, or position was changed. The strongest result is transferable receiver residual structure in DS26-0050; it does not explain enough of the target discrepancy to recover the track.

## Fixed protocol

The cases were evaluated in the prescribed order: DS26-0050, DS26-0223, then the inexpensive DS26-0251 check. Gaussian basis knots have fixed 6 s spacing and width, zero-mean coefficients have a fixed 150 Hz prior, witness noise is fixed at 150 Hz, and per-track nuisance constants have a 300 Hz prior. Receiver and satellite contributions scale with RF/11.5 GHz. No target values or target-estimated noise enter correction fitting; there was no hyperparameter search or selection using target improvement.

Receiver-only correction trains on other satellites on the target receiver. Satellite-only correction trains on the same NORAD on other receivers. The joint model adds receiver and satellite columns and uses their union of witnesses. These are different prespecified covariance hypotheses, not causal identifications.

Seed **20261031** selects one third of whole eligible witness components for holdout: training/held counts are **17/8**, **21/10**, and **14/6** respectively. The assignments are identical across both c arms and control/addition endpoints. All target observations are excluded from correction fitting and receiver calibration. Held curved components are removed before refitting baseline receiver coefficients. Original observation IDs are unique and disjoint across target, training, and held witness sets. Predictive entries compute residuals without updating baseline calibration coefficients.

Both c = 0 and fitted-c use matched observations, witness groups, candidate identity, knots, priors, and zero position-search budget. Geometry and phase references remain frozen at their saved endpoints. The existing per-track bias is reprofiled in both before/after variants. Correction fitting never consumes a target residual. All saved curved objectives replay exactly; the final diagnostic run took **6.70 s**, and **four tests passed**.

## Matched control metrics

Each cell reports **c = 0 / fitted-c**. RMS is in Hz. Baselines here include removal of held curved witnesses: 0050 **115.74 / 116.52**, 0223 **136.19 / 134.08**, and 0251 **160.14 / 160.06**. Compare corrections against these matched baselines, not against the earlier full-calibration residuals.

| Case | Correction | Corrected target RMS | Corrected lag-1 ACF | Exact failed noise screens, both arms |
|---|---|---:|---:|---|
| 0050 | Receiver | 98.73 / 99.64 | .600 / .607 | ACF |
| 0050 | Satellite | 114.80 / 115.69 | .700 / .703 | ACF |
| 0050 | Joint | 96.84 / 98.69 | .603 / .616 | Step, ACF |
| 0223 | Receiver | 129.54 / 127.35 | .593 / .581 | Slope, step, ACF |
| 0223 | Satellite | 132.89 / 131.59 | .609 / .602 | Slope, step, ACF |
| 0223 | Joint | 108.01 / 107.77 | .440 / .438 | Slope, step |
| 0251 | Receiver | 160.27 / 158.89 | .566 / .558 | ACF |
| 0251 | Satellite | 164.54 / 164.38 | .587 / .586 | ACF |
| 0251 | Joint | 159.63 / 159.58 | .554 / .553 | ACF |

The unchanged noise limits are mean z ≤ 3, slope z ≤ 3, quadratic BIC gain ≤ 10, maximum step z ≤ 4, and |lag-1 ACF| ≤ 4/√n. ACF bounds are **.455842**, **.447214**, and **.488678** for the three targets. Mean and quadratic screens pass after every tested correction. For 0050 joint, step z is **4.784 / 4.858**. For 0223 receiver, slope z is **4.004 / 3.911**, and step z **4.815 / 4.674**; satellite has slope **3.896 / 3.868** and step **4.836 / 4.714**. For 0223 joint, slope **4.208 / 4.237** and step **4.829 / 4.778** fail even though ACF passes and quadratic BIC is **8.595 / 8.618**.

Addition endpoints show the same pattern of failed screens. Specifically, 0223 joint addition has slope z **4.158 / 4.189**, step z **4.714 / 4.665**, ACF **.429 / .428**, and quadratic BIC **7.657 / 7.739**. Passing ACF alone is insufficient. Final-mean residuals, including their remaining trend and step, are what the unchanged screen evaluates.

## Held witnesses

Pooled RMS weights each held track by its number of observations. Cells again show **c = 0 / fitted-c**; the last column counts tracks whose RMS worsened, without introducing a new significance threshold.

| Case | Correction | Held tracks | Pooled RMS before → after, Hz | Worsened tracks |
|---|---|---:|---|---:|
| 0050 | Receiver | 3 | 85.41→74.28 / 86.35→74.50 | 0 / 0 |
| 0050 | Satellite | 1 | 28.65→28.69 / 28.88→28.40 | 1 / 0 |
| 0050 | Joint | 8 | 93.20→82.37 / 93.71→83.11 | 1 / 1 |
| 0223 | Receiver | 9 | 109.06→105.56 / 108.68→105.34 | 1 / 1 |
| 0223 | Satellite | 0 | No held witness in this fixed split | — |
| 0223 | Joint | 10 | 106.89→104.56 / 106.47→104.37 | 2 / 2 |
| 0251 | Receiver | 4 | 140.40→140.00 / 140.20→140.11 | 1 / 1 |
| 0251 | Satellite | 2 | 58.42→59.12 / 58.69→59.32 | 1 / 1 |
| 0251 | Joint | 6 | 113.75→115.03 / 113.66→115.27 | 2 / 2 |

For 0223 control fitted-c joint, the regressions are RX1 CH5 T002 **81.9→96.1 Hz** and RX1 CH6 T003 **111.3→119.5 Hz**. For 0251 the joint model worsens pooled held-witness RMS in both arms; RX1 CH5 T000 changes **102.7→129.2 / 101.9→128.4 Hz**. The 0050 joint model also worsens RX1 CH6 T006 **111.8→115.1 / 112.8→116.0 Hz** despite its pooled improvement. Complete track receipts are in [held_witnesses.csv](held_witnesses.csv).

## Interpretation and next experiment

This is a conditional residual covariance diagnostic. Frozen geometry and phase references were learned previously; held-track geometry is inherited. Addition geometry is target-informed, and control geometry excludes the target. Refitting receiver coefficients after holding tracks out does not remove that inherited geometry dependence. Cross-channel and same-satellite correlations also limit independence. The joint model cannot uniquely attribute discrepancy to receiver versus orbit/satellite effects. One randomized partition is not independent replication, and 0223 has no held same-satellite other-receiver witness in that partition.

No position accuracy was measured. Better residual RMS or frequency fit cannot establish better localization. No GPS, future TLE, new RF, relaxed threshold, or accepted association was used.

The next parsimonious experiment, if pursued, is a **DS26-0050 receiver-only leave-one-other-satellite-family-out check**, retaining the fixed 6 s model and 150 Hz noise/prior. Randomize whole families reproducibly; fit preprocessing, geometry, and receiver calibration using training evidence only, then evaluate the held family and untouched target with matched c arms and unchanged gates. This tests whether the receiver component generalizes across satellite identity, rather than adding a target-specific drift or richer joint model. Stop at a bounded negative result; do not attempt inclusion while any gate fails. No such additional fit was performed here.

See [result.json](result.json), [summary.csv](summary.csv), and the matched correction plots: [0050](DS26-0050.png), [0223](DS26-0223.png), [0251](DS26-0251.png). PDFs are alongside the PNGs.
