# Correlation and receiver-cone ablation

All four cells use the same normalized q=0.20 trend mixture, panels, masks and one-timing-per-scan geometry. q020 and soft40 are published zero-correlation controls; the two corr10 cells are the new ten-second covariance fits. The correlation change applies to both signal and background. Soft40 changes training candidate priors with shared nominal axes. Held density is normalized in the same frequency-contrast coordinates. No setting was selected by reference error.

Median horizontal errors in metres, requiring all three block audits. These are comparisons to an exposed unsurveyed reference.

| Model | DS7 four | DS7 eight | DS8 four | DS8 eight | DS9 four | DS9 eight |
|---|---:|---:|---:|---:|---:|---:|
| q020 | 2,196.1 | 2,023.6 | 2,473.8 | 1,721.1 | 1,173.9 | 876.1 |
| soft40 | 2,213.3 | 2,014.5 | 2,456.3 | 1,692.8 | 1,196.6 | 717.1 |
| corr10 | 2,487.6 | 1,971.8 | 1,626.0 | 1,936.5 | 1,551.2 | 2,059.2 |
| corr10_soft40 | 2,391.6 | 2,241.1 | 1,629.5 | 1,964.6 | 544.7 | 1,942.5 |

| Change | Audited pairs | Lower geographic error | Better held prediction | Median held change (nats) |
|---|---:|---:|---:|---:|
| q020 → soft40 | 18 | 11 | 10 | +0.498 |
| q020 → corr10 | 18 | 9 | 18 | +4365.533 |
| soft40 → corr10_soft40 | 18 | 9 | 18 | +4361.134 |
| corr10 → corr10_soft40 | 18 | 9 | 10 | +1.463 |

Counts across nested panels and model contrasts are dependent. Higher predictive density is not proof of better geographic accuracy. All per-panel cells and failed-audit status remain in ablation.json; medians never silently omit an invalid block.

![Matched eight-scan median errors](ablation.png)

[All cells](ablation.json), [full fits and audits](all-complete/README.md).
