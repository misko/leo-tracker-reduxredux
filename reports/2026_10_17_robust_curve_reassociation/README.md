# Robust polynomial membership and satellite reassociation

The T009 correction generalizes as a conservative membership check, but fixes
only two observations across all five DSX01 scans. Scan 1 recovers the other
26 T009 observations for satellite compatibility. Broader refitting exposed an
objective mismatch: low squared error can reward states whose residuals later
fail whole-track noise checks. None of these experiments establishes sub-0.5 km
localization or authenticated satellite identity.

## Membership without satellites or a position

Degrees 1–4 compete under the existing Gaussian/clutter EM contrast, 150 Hz
noise, 2% clutter probability, fixed 227.273 kHz clutter width, and
`(degree+1)*log(original count)` penalty. All points contribute to every final
score; there is no random or time holdout. Alias branches, measured times, CFOs
and original IDs remain unchanged. Rejected members remain explicit background.
The catalogue adapter verifies a lossless partition and the merger consumes that
same supplied population instead of reloading old memberships.

DSX01 contains 676 Graph fragments and 18,338 Graph points. Two become explicit
background: S01/RX1/CH1/T009's endpoint and S02/RX1/CH4/T002's point at
82.144211 s, 27.561 kHz from its fitted core. Both were already unassociated.
DS22-001 has 111 fragments, 3,510 Graph points and no membership changes.
Polynomial metadata changes alone cannot affect this physical matcher: it uses
the original measured CFOs, times and RF. Exact numerical-input fingerprints
justify reuse of DSX01 S03–S05 and DS22's unchanged controls.

T009's robust quadratic fits 26 points at 115.4 Hz RMS; its last measurement is
9.451 kHz away after an 8.166 s gap. Cubic and quadratic scores nearly tie;
robust degrees 2–4 all reject that same endpoint. At one of nine tested noise /
clutter settings the all-point quartic wins, so this is a declared sensitivity,
not a universally calibrated outlier rule. The endpoint has independently
qualified pilot CFO and remains a valid, unassociated measurement. See the
[detailed T009 review](../2026_10_17_dsx01_polynomial_satellite_dive/t009_robust_order/README.md).

## Coverage at the supplied position

GPS is fixed at 37.849061591561885, -122.48574968092912, height 0 m. This section
measures frequency compatibility, not localization. Causal candidate banks,
other priors and budgets are matched between c=0 and fitted-c. Scan-local RX / band
offsets and drifts remain; drift sigma is 0.5 Hz/s and bound 1 Hz/s. Only raw
measured-curved tracks calibrate hardware or phase. Linear tracks can associate
after calibration. Shared-constant joins require member and pooled residual
checks with at most a 30 s gap. All original point IDs are retained.

| Scan | c arm | Original | Raw refit | Safeguard | % raw GLRT | Merged tracks | Points / track |
|---|---|---:|---:|---:|---:|---:|---:|
| DSX01-S01 | c0 | 1,975 | 2,001 | 2,001 | 41.71% | 70 | 28.6 |
| DSX01-S01 | fitted_c | 1,975 | 2,001 | 2,001 | 41.71% | 67 | 29.9 |
| DSX01-S02 | c0 | 1,868 | 1,868 | 1,868 | 53.01% | 56 | 33.4 |
| DSX01-S02 | fitted_c | 1,857 | 98 | 1,857 | 52.70% | 56 | 33.2 |
| DSX01-S03 | c0 | 2,674 | 2,674 | 2,674 | 67.05% | 74 | 36.1 |
| DSX01-S03 | fitted_c | 2,649 | 2,649 | 2,649 | 66.42% | 62 | 42.7 |
| DSX01-S04 | c0 | 1,978 | 1,978 | 1,978 | 53.19% | 59 | 33.5 |
| DSX01-S04 | fitted_c | 1,995 | 1,995 | 1,995 | 53.64% | 55 | 36.3 |
| DSX01-S05 | c0 | 1,876 | 1,876 | 1,876 | 46.25% | 60 | 31.3 |
| DSX01-S05 | fitted_c | 1,876 | 1,876 | 1,876 | 46.25% | 60 | 31.3 |

Percentages use all 20,084 raw GLRT detections, including detections outside the
18,338-point Graph catalogue. Graph-only percentages would be higher. The
safeguarded totals are 10,397 / 20,084 (51.77%)
for c=0 and 10,378 / 20,084
(51.67%) for fitted-c. Changes in frequency fit
do not establish a position advantage for either c arm.

![All-scan coverage](coverage_comparison.png)

## Why the raw S02 refit is not adopted

S02 fitted-c falls from 1,857 to 98 compatible points: 25 gained, 1,784 lost,
with no relabelled retained IDs. On the same repaired population, the old scalar
score actually prefers that 98-point state (227.35 million versus 282.67
million). This is not merely choosing a worse numerical minimum. The objective
rewards residual energy before later rejection of structured residuals.

The new experimental score first applies visibility, constant, RMS and each
member's noise gates to every candidate, then ranks feasible candidates. A
component with none pays `min(count,50)*900Hz^2`. Bias, phase, drift and
conditional phase-volume terms remain, with a hardware dimension penalty.
Only individually measured-curved fragments can rank states; linear / background
fragments have no indirect calibration vote. This composite score is not an
identity probability or a calibrated false discovery rate.

`track_evidence_audit/` rescored saved states. Its safeguard compares only the
original and repaired parameter proposals at the **same supplied position**;
it does not optimize new parameters or use the GPS state to initialize a blind
geographic search. Bad raw refits remain available for diagnosis. This small
state-pool safeguard is not a completed new localization algorithm.

In this saved-state audit the new score also prefers the known-position state
over both saved blind S01 states, and over the saved DS22 cold state, in both
c arms. For repaired S01 c=0 the comparison is 1,265.07 versus 1,385.11 million
for the known-position and resumed-blind states; for DS22 c=0 it is 1,305.99
versus 1,455.31 million. This is encouraging diagnostic discrimination, but the
GPS state was already present in the audit pool. It is not a new blind result.

![Objective disagreement](objective_comparison.png)

## Actual position evaluation

Independent cold searches use the same 125 km / 13-point grid, one retained
basin, approximate discovery and three exact finalists. Reference coordinates
are applied only after saving the blind result. This sparse search misses a
better known DSX01 basin, so its result is budget-specific.

| Dataset / search | Original c=0 / fitted-c error, km | Repaired c=0 / fitted-c error, km |
|---|---:|---:|
| DSX01 S01, cold sparse grid | 41.733 / 41.734 | 41.595 / 41.595 |
| DSX01 S01, resumed local blind | 12.530 / 12.530 | 12.530 / 12.530 |
| DS22-001, cold sparse grid | 14.816 / 14.816 | 14.816 / 14.816 |

The resumed comparison initializes all arms from the same earlier sealed blind
c=0 state, then searches 26 locations within a matched 33-location local
budget, with three exact finalists. It is separate from the cold benchmark.
Both original and repaired arms end at the identical position and associate
1,814 points. The old objective improves from 172.08 to 151.25 million after
repair without improving position. DS22's observations are numerically
unchanged. Only DS22-001 was evaluated in this iteration; no whole-DS22 accuracy
claim is made. The <0.5 km objective remains unachieved.

## Reproducibility and next experiment

Partition receipts bind original catalogues and every output; equivalent-input
reuse receipts bind physical inputs and priors. `fits/`, `resumed/` and
`fixed_cohort/` retain protocols, fits, associations, merger outputs and explicit
background accounting. `baseline_run_code_snapshot/` preserves the sources used
for the completed old-objective experiments, before adding the optional
phase-information mask. `track_evidence_audit/` records exact input-state hashes
and new-score parts. Original published catalogues and sealed reports are intact.

Twenty-eight focused tests pass for robust degree selection, a supported genuine
quartic, point ownership, partition validation, supplied-population consolidation,
numerical equivalence, phase penalties and feasible-candidate ranking. The next
bounded experiment is to optimize the noise-gated score in a GPS-independent
search, with matched c arms and conditional null controls. Rescoring a pool that
already includes the known-position fit cannot establish blind accuracy.
