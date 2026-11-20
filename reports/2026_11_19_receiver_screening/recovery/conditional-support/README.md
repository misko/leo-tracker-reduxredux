# What caused the added-support RF errors

On DS26-0197, both added RX2 components belonged to NORAD 67348. The original fitted its phase at +14.29 s for `c = 0` and +14.26 s for fitted `c`. Every expanded owner-model fit stopped at the lean +7.5 s limit, including the versions with a smooth receiver clock or diagonal frequency noise. Releasing only that family’s bound in a fixed-owner ablation reduced added-support RMS from 9.24/9.20 kHz to 219/218 Hz. The independent blind rescue did not establish the original owner. Both simultaneous channels preferred the same competing orbit by a narrow margin. [Point-level evidence](DS26-0197-points.jsonl.gz) · [Forced-only refit](DS26-0197-oracle-refit.json)

## Exact input and model audit

The audit selected 71 extra conditional observations on DS26-0197 and 495 on DS26-0223 from the sealed common and expanded owner-model outputs. Original estimator observations, regenerated native Graph samples and lean rows matched on identity, exact double-precision timestamp, CFO harmonic lift and actual RF. Both arms matched on all 566 points. Original v5 and the lean receiver used the same causal TLE bytes for every affected orbit. The original and lean range-rate interpolators differed by 0.22–0.34 Hz RMS over these points. This rules out timestamp, alias indexing, TLE selection, and interpolation as explanations for the large residual. The 67348 lines hash to `b59161d8151c97b6bd80f34bdeeef15faaa63f6cbd8c65fa0b33bc48768e4fde` at epoch 1793096361527328000 UTC ns and were collected about 1.49 h before capture. [Numerical protocol](PROTOCOL.md) · [DS26-0197 component ledger](DS26-0197-components.json) · [DS26-0223 component ledger](DS26-0223-components.json)

The waterfall inserts the archived position, original causal element, archived phase, and archived receiver clock in order, keeping the same observations and harmonic lift. The final column restores the frequency difference implied by the original conditional residual. This measured remainder combines conditional orbital and component-offset terms. The archived frequency-event count was zero in both cases. These diagnostic results use original archived calibration and geographic parameters.

| Added-support RMS, Hz | Lean expanded | Archived site and element | Add archived phase | Add archived radio clock | Original conditional |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS26-0197 · `c = 0` | 9,238 | 17,440 | 4,295 | 774 | 19.85 |
| DS26-0197 · fitted `c` | 9,205 | 17,317 | 4,319 | 762 | 19.85 |
| DS26-0223 · `c = 0` | 616 | 4,072 | 2,980 | 133 | 66.47 |
| DS26-0223 · fitted `c` | 617 | 4,090 | 2,984 | 126 | 66.47 |

At the DS26-0197 archived site, changing the phase moves predicted CFO by 21.70/21.60 kHz RMS. The expanded lean fit partly compensated by moving position, which accounts for 8.21/8.12 kHz of model difference. The clock difference was 3.56/3.59 kHz RMS, while the original smooth clock term itself contributed 23/25 Hz. Applying the original clock and keeping the lean phase ceiling still leaves 20.6–21.5 kHz RMS on the two components. After matching phase and clock, the remaining DS26-0197 prediction discrepancy includes a slope around −27 Hz/s on both nearly simultaneous carriers and distinct average offsets of about 0.6–0.8 kHz. The full archived model accounts for that common structure, but this audit does not identify a unique physical source. DS26-0223 has corresponding phase saturation at −7.5 s for four 67315 components, plus mismatches on five other orbit families whose fitted phases did not hit the limit. [Fixed-point decomposition and position chart](mechanism-and-forced-refit.png)

## Forced position under identical owners

Using published v5 owners and lifts as privileged inputs, the fixed-alias, fixed-owner numerical control reproduced both previous forced coordinates exactly. The expanded refit kept every point, receiver model, phase prior scale, other satellite bounds, orbit bank, interpolation alignment, optimizer and search tile. It changed only the two-sided phase limit for the saturated family from 7.5 to 22.5 seconds. Zero/fitted calibration arms were otherwise matched. All coordinates in this ablation are forced diagnostic outputs.

| Model | Source phase before → after | Added RF RMS before → after | Forced GNSS error before → after |
| --- | --- | --- | --- |
| DS26-0197 · `c = 0` | +7.500 → +14.606 s | 9,238 → 219 Hz | 18.726 → 3.113 km |
| DS26-0197 · fitted `c` | +7.500 → +14.397 s | 9,205 → 218 Hz | 18.726 → 2.156 km |
| DS26-0223 · `c = 0` | −7.500 → −9.837 s | 616 → 142 Hz | 9.549 → 0.747 km |
| DS26-0223 · fitted `c` | −7.500 → −9.906 s | 617 → 150 Hz | 9.549 → 1.214 km |

The improved DS26-0197 error is still worse than the original blind joint forced prediction at 1.884/1.189 km. DS26-0223 improves on its original blind forced error at 1.635/1.832 km. Broad causal widening has already reduced publication coverage across the 135-case blind roof panel. This decomposition shows that the phase limit matters when the orbit association is correct. [DS26-0223 refit](DS26-0223-oracle-refit.json) · [Blind causal-width panel](../../refinement/phase-support/README.md)

## Blind cross-component rescue

The new receiver reruns the original joint gate only if the nominal receiver withholds and two unused curved training arcs independently choose the same satellite beyond the nominal phase limit. Each track must also predict the other’s orbit phase and tile point under the frozen training clock, and its leading identity must beat the nearest competitor by 0.25. The original held tracks never choose the orbit or train its clock. The alternate fit inherits the original gate and keeps the nominal output when it withholds.

On DS26-0197 the independently searched 41- and 30-point RX2 supports ranked 66330 first at −12 s with costs 0.009 and 0.021. Both ranked 67348 second at +15 s with costs 0.104 and 0.072. The two costs per orbit come from different channels of one receiver over the same time interval. This is reproducible RF evidence with limited independent orbital geometry. Relaxing the acceptance margin here would favor 66330. Both diagnosed roof cases and both DS26 confirmations kept their original withholds. The two DS29 confirmations published unchanged, yielding 2/4 in the confirmation cohort under each method and arm. [Exact blind competitor ranks](blind-rank-near-miss.json) · [Both-arm geometric comparison](blind-matched-positions.png)

The authentic omitted offer put GNSS 38.61 km outside the tile. It yielded two reciprocal orbit proposals, 62320 at −8 s and 57908 at −9 s. The refit tried the higher-ranked 62320, and the original held-track gate rejected it in both arms. Forced errors in the trial branch were 42.54/42.82 km. The receiver retained the nominal forced errors of 38.88/38.91 km and published no position. The seven end-to-end workers ran in 73.9 s over three cores. Median worker CPU was 5.50 s versus 4.98 s on the separately scheduled archive; all seven final output arms and RF fits were exactly unchanged. [Sealed blind predictions](prediction-lock.json) · [Matched score records](scores.csv) · [Committed inputs and sources](blind-plan.json)
