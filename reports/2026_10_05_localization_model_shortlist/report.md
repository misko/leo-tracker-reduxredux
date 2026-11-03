# DS13 localization model shortlist and performance

Evidence snapshot: 6 October 2026. Here **N16 means the N01–N16 cohort**; the
individual N16 result is also included below. All positions are estimated
independently, never jointly across scans.

The three full-data model variants worth retaining are **C1-Q1 as the reference,
V16 as the tuned-likelihood challenger, and C1-TIME-Q1 as the temporal-weighting
challenger**. These are a practical shortlist, not three proven winners. No model
dominates individual-scan accuracy, mean error, median error and both RF arms.

The saved N01–N16 results support this shortlist. **The exact three configurations
have not been compared on A/B.** A/B's historical T1-AT v1 results are reported
separately rather than attributed to newer models. There is no complete matched
18-scan tournament to summarize yet.

## Baseline and model complexity at a glance

**T1-AT v1** is the original baseline referred to as "v1at". The comparison below
keeps it alongside the three shortlisted variants. T1-AT v1 is the shared
association approach; its historical position baseline uses the original soft
score and relative timing sigma 1 s.

Complexity is a qualitative gauge of the **position model and its implementation**:
1/5 means a simple fixed-identity fit; 3/5 means soft satellite competition with
joint position, receiver and timing nuisance fitting; 5/5 would mean substantial
additional learned structure or latent processes. Half steps indicate small
implementation additions, not measured differences. This is neither a runtime
benchmark nor a measure of localization quality.

| Model | Approach | Complexity gauge | Additional fitted parameters versus baseline | N median fitted c | N median c=0 |
| --- | --- | --- | ---: | ---: | ---: |
| T1-AT v1 historical baseline | Top-one refined GLRT, greedy + replacement, original soft position score | 3/5 — moderate | Reference | 1,553 m* | 2,000 m* |
| C1-Q1 | Tighten relative timing prior; smooth the horizon gate | 3/5 — essentially the same | 0 | 1,288 m | 1,531 m |
| V16 | Retune frequency width, signal/clutter odds and timing priors | 3/5 — same model structure | 0 | 1,167 m | 1,280 m |
| C1-TIME-Q1 | C1-Q1 plus fixed temporal-density weights | 3.5/5 — small additional weighting step | 0 | 1,277 m | 1,368 m |

`*` The historical baseline uses a **2 km** search, with **6/16 fitted-c and
9/16 c=0 results on the boundary**. The newer rows use 4 km. The historical
baseline also has different calibration, selected windows and search history;
these are not matched improvement percentages. After its saved convergence
retry, 15/16 fitted-c and 14/16 c=0 fits converged. Baseline source:
[all-window historical position results](../2026_10_04_t1_at_v1_replication/convergence-retry/position-results.csv).
The later A/B snapshot remains in its separate table below.

For a fixed bank of `K` satellites, **all four position models fit the same
number of independent parameters**:

- Two horizontal position coordinates.
- Four receiver terms: offset and slope for each of RX0 and RX1.
- `K` timing degrees of freedom: one common shift plus `K−1` relative shifts.
- One RF coefficient when `c` is fitted.

That is **K + 7 parameters with fitted c**, or **K + 6 with c = 0**. For example,
33 satellites means 40 or 39 fitted parameters. The earlier receiver spline
calibration and discrete satellite selection are separate stages, not included
in this final-position parameter count. Different selected satellite counts
therefore change actual fit size even when the model family is unchanged.

V16 has **greater hyperparameter-tuning burden**, not greater fitted model
dimension: several settings were chosen together on the development cohort.
C1-Q1 adds a deterministic visibility function. C1-TIME-Q1 adds deterministic
bin counts and weights, not an extra time-series model. All share the dominant
window-by-satellite likelihood calculation; total fitting time can still differ
because of convergence, satellite count and restart policy. No speed ranking
has been established here. The older fold-derived calibration is more involved
upstream than the newer full-scan calibration, independently of this position
complexity gauge.

## The common association and position pipeline

1. Start with the saved passing GLRT activity in each receiver/channel/20 ms
   window. Refine candidate frequencies and epochs from IQ without orbit input.
2. Keep the highest-refined-GLRT-margin candidate per window. Coverage counts
   these windows, not every acquisition hypothesis or alias copy. This top-one
   choice deliberately does not represent every simultaneous signal in a window.
3. Fit the receiver calibration on the full scan at the known roof. The newer
   N-cohort calibration uses no held-out folds, although the receiver spline
   uses supported/high-responsibility residuals rather than every point equally.
4. Search the visible satellite bank with absolute timing shifts within ±20 s.
   Use the existing coherent-support gates, including at least 10 points, and
   greedy selection followed by satellite removal/replacement. The discrete
   association objective is maximized:

   \[
   S=N_{\rm assigned\ windows}-10N_{\rm satellites}.
   \]

5. Freeze the selected observations and satellite bank for positioning. Keep all
   associated top-one windows, not just a favorable subset. The final soft model
   may redistribute responsibility among those satellites or clutter; the
   original greedy labels are not fixed identities in this likelihood.
6. Independently minimize the position score within a 4 km disk for each N scan,
   profiling receiver corrections, RF calibration and timing. Use matched
   fitted-`c` and `c = 0` arms with the same observations, bank, other settings
   and maximum search budgets within each experiment.

The numerical benchmark provenance is in the
[full-data association results](../2026_10_04_t1_at_v1_replication/full-scan-seed-restart/association-summary.csv),
[score study](../2026_10_04_t1_at_v1_replication/position-score-sweep/report.md), and
[visibility study](../2026_10_04_t1_at_v1_replication/position-visibility-study/polished/report.html).
T1-AT v1 names the association baseline; the names below identify its downstream
position-score variants, not three unrelated tracking algorithms.

## The shared position score

After subtracting the saved receiver baseline, the predicted frequency is

\[
\mu_{gs}=D_s(x,t_g+\tau+\delta_s;F_g)
 +a_{r_g}+b_{r_g}(t_g-150)
 +c\frac{F_g-F_{\rm ref}}{1\ {\rm GHz}}.
\]

Here `x` is position; `a` and `b` are additional receiver offset/drift corrections;
`tau` is common orbit timing; and `delta_s` is a satellite-relative timing shift
in the zero-sum parameterization. The saved nonlinear receiver baseline remains
fixed. The `c = 0` ablation disables the final RF coefficient, not every
RF-dependent operation in the upstream calibration.

For one retained observation per window, the finite-set likelihood specializes to

\[
q_{gs}=\frac{D}{|S|}v_{gs},\qquad
P_{0g}=e^{-\lambda}\prod_s(1-q_{gs}),
\]

\[
L_g=\frac{P_{0g}}{1-P_{0g}}
\left[\frac{\lambda}{A}
 +\sum_s\frac{q_{gs}}{1-q_{gs}}\phi_A(y_g-\mu_{gs};\sigma_f)\right],
\]

where `A` is the approximately 227.273 kHz alias period, `phi_A` is a wrapped
Gaussian density, and `v` is visibility. `D` is a detection-count budget, not a
single probability; the individual `q` values must be below one. `lambda` is
clutter rate, not a penalty on the RF coefficient `c`.

The minimized loss and position profile are

\[
J(x,\theta)=-\sum_g w_g\log L_g
 +\frac12(\tau/\sigma_\tau)^2
 +\frac12\sum_s(\delta_s/\sigma_\delta)^2,
\qquad J_*(x)=\min_\theta J(x,\theta).
\]

The spatial gradient describes the change of **this profiled score**, not the
gradient of assignment coverage or RMS. At a smooth converged nuisance optimum,
the envelope theorem gives the profile gradient from the spatial partial
derivative of `J`; switching local optima or interpolation knots can complicate
that interpretation. A lower score can still correspond to a worse position.

The common hard bounds are ±10 s common timing, ±20 s total satellite timing,
±50 Hz/s extra receiver slopes and ±5,000 Hz/GHz fitted `c`. Gaussian prior widths
are not those hard bounds. The tested variants below do not add a Gaussian
shrinkage prior on `c`.

## Three configurations to retain

| Setting | C1-Q1 reference | V16 tuned likelihood | C1-TIME-Q1 temporal weighting |
| --- | ---: | ---: | ---: |
| Frequency width `sigma_f` | 200 Hz | 125 Hz | 200 Hz |
| Detection budget `D` | 0.8 | 1.6 | 0.8 |
| Clutter rate `lambda` | 2 | 0.5 | 2 |
| Common timing prior sigma | 10 s | 3 s | 10 s |
| Relative timing prior sigma | 1/3 s | 0.15 s | 1/3 s |
| Observation weights | Equal | Equal | Inverse occupied-bin count |
| Visibility in the reported run | Smooth 0–1° horizon | Hard horizon | Smooth 0–1° horizon |

**C1-Q1** is the reference to keep. It uses soft competition between satellites
and clutter, modest frequency tolerance and a tighter relative timing prior.
Q1 is a smooth quintic horizon ramp: zero at/below 0°, one at/above 1°. It improves
numerical continuity without allowing below-horizon support; it did not materially
improve position error in the visibility experiment. It is not an antenna cone.

**V16** is the best cohort-median challenger in the sixteen-variant hyperparameter
study. It combines a narrower frequency likelihood, higher signal odds and tighter
timing priors. It does not simply "fit more accurately": it changes which residuals
and assignments influence the result. Its mean-error tradeoff prevents declaring
it the new default. Adding Q1 to V16 would be a new, untested combination.

**C1-TIME-Q1** reduces the influence of dense sampling bursts. Each occupied
original-satellite/receiver/5-second bin receives equal total observation weight;
all weights are then normalized to mean one. No windows are dropped. This is a
weighted/composite likelihood, not an explicit model of temporal correlation.
Its strongest evidence is improved performance without fitted `c`.

The compact aliases C1-Q1 and C1-TIME-Q1 refer to the saved `ordinary/Q1` and
`time-balanced/Q1` rows; V16 retains its existing experiment identifier.

## Performance on N01 to N16

All errors below are horizontal distance from the known roof, in metres. Each
row includes all 16 scans, including flagged fits. These are **saved study
snapshots**, not a fresh shared-start comparison of the three configurations.
V16 has a different optimization history from the two Q1 variants. Both RF arms
are controlled within each source study.

| Model | RF arm | Median error | Mean error | 90th percentile | Below 1 km | Converged | 4 km boundary |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| C1-Q1 | Fitted c | 1,288 | 1,584 | 2,589 | 3/16 | 16/16 | 0 |
| C1-Q1 | c = 0 | 1,531 | 1,907 | 3,815 | 2/16 | 14/16 | 2 |
| V16 | Fitted c | 1,167 | 1,609 | 2,570 | 4/16 | 16/16 | 0 |
| V16 | c = 0 | 1,280 | 1,763 | 3,391 | 4/16 | 15/16 | 1 |
| C1-TIME-Q1 | Fitted c | 1,277 | 1,568 | 2,634 | 3/16 | 16/16 | 0 |
| C1-TIME-Q1 | c = 0 | 1,368 | 1,686 | 3,685 | 6/16 | 16/16 | 1 |

Recomputed from the [per-scan visibility results](../2026_10_04_t1_at_v1_replication/position-visibility-study/polished/per-scan.csv)
and [per-scan score-sweep results](../2026_10_04_t1_at_v1_replication/position-score-sweep/polished/per-scan.csv).

### What the controlled comparisons actually establish

- In V16's own matched sweep, its C1 control had a **1,225 m median and 1,571 m
  mean**, not the later Q1 snapshot's 1,288/1,584 m. V16 improves median by 4.8%
  but worsens mean to 1,609 m. Six scans improve and ten worsen by more than 1 m
  with fitted `c`. The median paired change is **47 m worse**, despite the lower
  cohort median. These statistics answer different questions.
- C1-TIME-Q1 versus C1-Q1 is directly matched. Fitted-`c` aggregate improvement is
  small: median 1,288 → 1,277 m and mean 1,584 → 1,568 m, with seven scans improving
  and nine worsening by more than 1 m. With `c = 0`, median improves 1,531 → 1,368 m,
  mean 1,907 → 1,686 m, and ten scans improve versus five worsening.
- Frequency-fit quality is separate. Median posterior-weighted frequency RMS is
  **98.0 / 92.8 / 100.0 Hz** for C1-Q1 / V16 / C1-TIME-Q1 with fitted `c`, and
  **152.3 / 138.4 / 152.3 Hz** with `c = 0`. These responsibilities depend on the
  model, so they are not a common fixed-weight residual metric or identity proof.

### Individual scan errors

Within each model the columns are fitted `c`, then `c = 0`. `†` means unconverged;
`‡` means the 4 km boundary. A converged boundary result is still not an
unconstrained minimum.

| Scan | C1-Q1 c | C1-Q1 c=0 | V16 c | V16 c=0 | TIME-Q1 c | TIME-Q1 c=0 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| N01 | 250 | 1136 | 272 | 802 | 463 | 938 |
| N02 | 1185 | 1580 | 1143 | 1705 | 1216 | 1385 |
| N03 | 930 | 1065 | 987 | 1177 | 643 | 1352 |
| N04 | 1003 | 4000†‡ | 942 | 2930 | 1068 | 3390 |
| N05 | 2382 | 967 | 2574 | 535 | 2598 | 136 |
| N06 | 2460 | 2435 | 2557 | 2553 | 1891 | 1877 |
| N07 | 1311 | 1419 | 1079 | 1312 | 1012 | 1498 |
| N08 | 1109 | 177 | 991 | 456 | 1103 | 171 |
| N09 | 2807 | 4000†‡ | 3141 | 4000†‡ | 3287 | 4000‡ |
| N10 | 1643 | 2230 | 1692 | 2088 | 1828 | 2430 |
| N11 | 1094 | 1085 | 1190 | 1190 | 1134 | 1116 |
| N12 | 2718 | 1516 | 2566 | 1247 | 2671 | 960 |
| N13 | 936 | 1206 | 1026 | 1247 | 581 | 844 |
| N14 | 1266 | 1546 | 1106 | 615 | 1338 | 945 |
| N15 | 2399 | 2516 | 2549 | 2496 | 2444 | 1956 |
| N16 | 1852 | 3630 | 1926 | 3852 | 1821 | 3979 |

## What we can report for A and B

The historical soft T1-AT v1 position baseline uses relative timing sigma **1 s**
and a **2 km search radius**, unlike the newer full-data N shortlist. Its archived
receiver baseline and local-search history also differ. A is **10 MS/s**; B and
all N scans are **2.5 MS/s**. A/B cannot be pooled into a matched 18-scan statistic
for the shortlisted configurations.

| Scan | Associated top-one windows | Coverage | Position error fitted c | Position error c=0 |
| --- | ---: | ---: | ---: | ---: |
| A | 3,644 / 3,837 | 94.97% | 180 m | 1,085 m |
| B | 3,460 / 3,602 | 96.06% | 1,142 m | 1,959 m |

Coverage is the fitted-`c` association arm; those same assigned observations are
used for both position arms. All four reported position fits converged.
Sources: [historical coverage](../2026_10_04_t1_at_v1_replication/cohort-coverage.csv)
and [A/B baseline position results](../2026_10_05_ab_ambiguity_prototypes/results.csv).

The often-quoted **B = 1,129 m** is an earlier saved local solution. The 1,142 m
figure above is the baseline snapshot used by the A/B ambiguity experiment;
neither should be presented as the result of C1-Q1 or V16. An earlier
[cross-evaluation audit](../2026_10_04_t1_at_v1_replication/historical-position-audit.json)
confirmed that different basins/search histories matter.

| Configuration | N01–N16 | Exact A/B results |
| --- | --- | --- |
| C1-Q1 | Available | Not evaluated in this exact configuration |
| V16 | Available | Not evaluated in this exact configuration |
| C1-TIME-Q1 | Available | Not evaluated in this exact configuration |
| Historical T1-AT v1 position baseline | Older results available | Available above |

## Coverage and the latest refinement experiment

All three shortlisted position snapshots use **42,610 associated windows out of
46,775 passing N-cohort windows: 91.10% coverage**. Final-score changes do not
rerun greedy selection or create additional association coverage. The separate
`c = 0` association diagnostic recovered 42,576 windows, but it is not the input
population used for the matched position ablation.

The latest experiment reran calibration, selection and shared-start position
optimization for each measurement stage. Its C1-Q1-family results are:

| Measurement stage | Fitted-c assigned windows | Median error fitted c | Median error c=0 |
| --- | ---: | ---: | ---: |
| Unrefined | 42,550 | 1,407 m | 1,756 m |
| Existing orbit-free refinement | 42,614 | 1,469 m | 1,452 m |
| One additional refinement pass | 42,614 | 1,467 m | 1,454 m |

These numbers do not replace a matched V16/time-weighting comparison: those
challengers were not rerun on these freshly calibrated inputs. They also show
why **"the baseline error" needs a data and search snapshot**, not just a model
name. Changed calibration, four additional assigned windows and further basin
search can alter position estimates while frequency RMS barely changes.

The extra IQ refinement pass changed only one winning-window frequency by more
than 100 Hz and gave no material coverage or localization benefit. Eight of the
96 position fits remained unconverged, and raw N05 had an upstream calibration
warning. Full results and flags are in the
[refinement comparison](../2026_10_05_n16_glrt_refinement_ablation/comparison/report.html).

## Promising historical results and changes not promoted

**Per-satellite drift remains worth retesting, but is not a clean full-data
winner.** Adding one receiver-shared, RF-scaled slope per satellite with a
zero-centered 2 Hz/s Gaussian prior reduced fitted-`c` median error from
1,440 to **1,126 m** and mean from 1,709 to 1,518 m in its matched historical
experiment. However, it used older fold-derived receiver calibration and only
41,092 associated windows; two fitted-`c` cases were unconverged and two hit
4 km. Without fitted `c`, median worsened 2,177 → **2,446 m**. It models residual
discrepancy, not established transmitter drift. Those differences prevent using
1,126 m to declare it superior to the current shortlist.
[Drift audit](../2026_10_04_t1_at_v1_replication/satellite-drift-localization/polished/audit.json).

Other useful findings are retained without promoting them to defaults:

- V12's tighter timing plus 125 Hz likelihood gave five sub-kilometre fitted-`c`
  results, but a worse mean and substantially weaker `c = 0` median than V16.
  [Score study](../2026_10_04_t1_at_v1_replication/position-score-sweep/report.md).
- A narrow/broad frequency mixture helped the `c = 0` tail but worsened the
  fitted-`c` median. [Structural study](../2026_10_04_t1_at_v1_replication/position-structure-study/report.md).
- Cone weighting in positioning had small mixed effects; cone-based selection
  caused substantial regressions. [Cone study](../2026_10_05_cone_prior_localization/report.html).
- Dropping ambiguous windows, hard assignments and ambiguity penalties did not
  consistently beat the N-cohort soft baseline.
  [Ambiguity study](../2026_10_05_n16_ambiguity_prototypes/report.html).

## Recommendation and limits

Keep **C1-Q1 as the reference**, carry **V16 and C1-TIME-Q1** as explicit
challengers, and retain historical satellite drift as the next structural
retest. Do not pick a different model per scan by looking at its known location.

The next meaningful comparison is a single frozen full-data input generation
for A, B and N01–N16, with the same 4 km radius, shared starts, optimization
budgets and paired RF arms for all three configurations. It has not been run as
part of this summary. Keep fitted-`c` and `c = 0` results separate; lower
in-sample frequency RMS or higher assignment coverage is not better localization
by itself.

These are development results on repeatedly examined scans with known-roof
upstream calibration, not blind localization validation. No new train/test
split is required to preserve full-scan fitting, but generalization claims need
new scans evaluated with configurations fixed in advance. Bounded local searches
and KKT convergence do not certify global minima.

## Reproducible evidence

This summary performed no new RF collection, refinement, association or position
fit. [summarize.py](summarize.py) recomputes aggregate and per-scan tables from
saved results, verifies complete cohorts and RF-arm observation counts, and
records source hashes. It does not substitute count checks for the original
source studies' bank/observation binding audits or repeat their numerical fits.

- [Numerical summary and source hashes](summary.json)
- [Per-scan values including controls and historical drift](per-scan.csv)
- [Summary checks](test_summary.py)
