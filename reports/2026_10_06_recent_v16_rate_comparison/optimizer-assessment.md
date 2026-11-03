# Assessment of optimizer changes on recent scans

Two optimizer-only experiments preserve the original dataset, satellite selection, likelihood, priors, and 4 km position constraint. Neither replaces the fixed-budget baseline. These are targeted development checks, not a cohort-wide validation.

## Longer continuation resolves some provisional fits

Across the first eight complete scans, continuation has processed 128 configurations. Of 29 initially unconverged fits, 23 now pass the unchanged convergence check; six remain provisional. Those six are four original-data R100-02 T1-AT fits, R025-05 original T1-AT cone-on c = 0, and R025-05 refined V16 cone-off fitted c. Already-converged results are retained unchanged. This is an eight-scan development snapshot, not the completed 16-scan comparison.

R025-01 had three nonconverged configurations. All three passed the unchanged stationarity check after bounded continuation. Their position errors changed by approximately +60 m, -2 m, and -0.3 m. Improving numerical convergence did not meaningfully improve localization there.

For R100-02 original measurements, V16 with cones off and fitted c improved from 1,968.5 m to 1,611.1 m and reached checked convergence. The prior 1,968.5 m result was unconverged. This is an optimizer improvement relative to a provisional result, not a new likelihood or demonstrated improvement on all scans. The original-data T1-AT cases remain difficult and near the search boundary.

All eight refined R100-03 configurations now pass convergence. The V16 comparisons illustrate why both the cone and RF ablations matter:

| R100-03 refined V16 setting | Fixed-budget error (m) | Continued error (m) | Continued convergence |
| --- | ---: | ---: | --- |
| Cones off, fitted c | 2018.4 | 2018.4 | Pass |
| Cones off, c = 0 | 617.7 | 756.3 | Pass |
| Cones on, fitted c | 947.3 | 947.4 | Pass |
| Cones on, c = 0 | 417.7 | 419.9 | Pass |

Cones improve position accuracy in both RF arms for this scan, but this does not establish a general benefit. Continuing the cone-off c = 0 fit substantially lowers its objective while increasing position error by 138.6 m. A small provisional error therefore cannot substitute for convergence checks, and convergence still does not certify the global optimum. The controlled comparisons retain the same refined measurements, selected satellites, and fixed receiver calibration; c = 0 here disables the final RF correction, not the RF term in upstream calibration.

R025-05 adds a counterexample to treating refinement or convergence as a cure for position bias. Its refined T1-AT fits remain about 2.30–2.37 km from the roof after passing convergence. All four refined V16 configurations reach the 4 km boundary; three pass convergence after continuation and one remains provisional. These are constrained results, not estimates of an unconstrained minimum. No search-radius change is made within this comparison.

The [continuation report](factorial-v1/continuation-v1/report.md) preserves every before/after result, including cases that do not converge or improve position. The [responsibility audit](factorial-v1/continuation-v1/responsibility-audit.md) shows why lower loss must not be equated with better location: the R025-01 original V16 cone-on fitted-c continuation changed the most probable state of 88 windows, mostly from clutter to satellite, while position error increased.

![Position error and objective changes for initially unconverged configurations](factorial-v1/continuation-v1/continuation-effects.png)

## Loss scaling is not ready to become the default

The matched R100-02 pilot compares 60 seconds of ordinary SLSQP against 60 seconds with loss and gradient divided by the number of associated windows. Final scores and convergence checks always use the original unscaled objective. A post-hoc follow-up offers all four RF/optimizer combinations the same additional 10-second Fisher budget.

| RF arm | Ordinary SLSQP plus polish KKT | Per-window scaling plus polish KKT | Scaled solution loss minus ordinary solution loss |
| --- | ---: | ---: | ---: |
| Fitted c | 4.17555 | 0.000576725 | +107.1661 |
| c = 0 | 17.5364 | 0.00122081 | +38.2233 |

The convergence tolerance remains 0.001. Scaling therefore passes for fitted c and narrowly fails for c = 0. Ordinary SLSQP is less stationary but has lower loss in both arms. All polished points lie on the 4 km boundary. Scaling helps reach stationarity in one case, but does not establish a better basin or better localization; it should not replace the current optimizer solely because its convergence flag looks better.

The [initial pilot](factorial-v1/optimizer-scaling-v1/report.md) and [matched polish report](factorial-v1/optimizer-scaling-v1/polished-report.md) contain exact results and reproduction commands. [Sampled finite-difference checks](gradient-check.md) support the local analytic gradients at the earlier difficult continuation point; no tested perturbation crossed a visibility mask.

## Implications for further optimization

Keep solver convergence, objective value, and position error as separate acceptance criteria. Preserve alternative basins instead of retaining only the first stationary result. Any broader scaling test should give every model and RF arm the same allowed starts and budgets, and select by the unchanged objective rather than known position.

Before tuning more model hyperparameters, finish the frozen scan comparison. R100-02's original association uses 54 satellites for 73.7% window coverage; its refined branch uses 40 satellites for 91.7% coverage. This substantial upstream difference deserves investigation alongside optimizer behavior. Better coverage is not proof of correct satellite identities or lower position error.
