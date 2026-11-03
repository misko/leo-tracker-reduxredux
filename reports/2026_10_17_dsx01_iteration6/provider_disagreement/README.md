# Causal HF versus Space-Track orbital disagreement

Seven of211 jointly available/valid original selected recording–satellite pairs
have provider disagreement exceeding10 seconds of effective along-track motion.
Four of215 selected pairs are not jointly comparable and remain explicit.
Large orbital disagreements exist, but these are not physical truth labels or
a calibration for all fitted timing shifts.

| Source | Jointly comparable /selected | Median abs equivalent seconds | 95th percentile | Maximum | >10s |
|---|---:|---:|---:|---:|---:|
| S01 | 46/46 | 0.162 | 4.693 | 14.843 | 1 |
| S02 | 48/51 | 1.465 | 10.122 | 27.953 | 3 |
| S03 | 39/40 | 1.923 | 8.716 | 13.149 | 2 |
| S04 | 46/46 | 1.201 | 5.082 | 6.626 | 0 |
| S05 | 32/32 | 1.522 | 5.238 | 24.476 | 1 |

For the previously discussed S01 object69522, the HF-minus-ST projected
difference is+0.916 seconds and the perpendicular discrepancy64m. This does
not explain a tens-of-seconds timing requirement for that object by provider
disagreement alone. Neither provider is declared truth.

For every source, select each provider's latest archive collected strictly
before recording start minus505seconds, matching the public cold pipeline's
causality padding. Propagate both at the recording midpoint, using three nearby
instants required by the public grid contract and selecting the exact midpoint.
The original215 selected object IDs define a descriptive cohort; no RF values,
fitted shifts or station coordinates enter the computation.

With HF-minus-ST displacement dr and ST ECEF velocity v, report
`dt_equiv = dot(dr,v)/dot(v,v)` and the perpendicular remainder. This is a
local displacement projection, not a fitted time correction or a physical
covariance. Max perpendicular discrepancies range2.59–6.60km across sources,
so orbital disagreement is not always represented well by shifting time alone.

The existing71/215 original fitted relative shifts above10seconds and these
7/211 provider discrepancies have different meanings. The first is a joint
frequency-fit parameter that can absorb geography/calibration/identity errors;
the second is disagreement between two imperfect predicted orbits. Do not
equate them or use the current fitted shifts to tune an orbital-error prior.

`pairs.csv` retains every selected ID and availability status; `summary.json`
pins each causal snapshot, collection time, cutoff, source cohort and script.
Archive reads verify payload hashes. Two component tests cover projection units,
sign, perpendicular components and rejection of zero reference velocity.
No fitting, provider selection by position accuracy, production or RF change.
