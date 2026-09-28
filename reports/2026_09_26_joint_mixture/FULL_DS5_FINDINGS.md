# DS5 joint-model evaluation: findings

Completed all 42 scans / 1,739 tracks with zero run failures. Seven completed scans were reused after model/input hash checks; 35 new scan jobs completed successfully. Eight tests pass. Model, numerical core, historical calibration, candidate shortlists, noise settings and inference settings were held fixed. No new geographic search, cross-site proposal sharing, production changes or RF collection.

## Main comparison

Counts indicate the known location has lower composite predictive NLL than the existing estimate. They are not localization-success counts. Frozen IDs use the same historical timing integration and block likelihood as the joint models, not the production baseline.

| Noise (Hz) | Model | Known preferred to Sacramento | Known preferred to Reno |
|---|---|---:|---:|
| 100 | Frozen IDs, no scan clock | 25/42 | 30/42 |
| 100 | Joint IDs, no scan clock | 26/42 | 27/42 |
| 100 | Joint IDs + scan clock | 31/42 | 28/42 |
| 200 | Frozen IDs, no scan clock | 26/42 | 30/42 |
| 200 | Joint IDs, no scan clock | 28/42 | 26/42 |
| 200 | Joint IDs + scan clock | 29/42 | 27/42 |

At 100 Hz, mean known-minus-estimate gaps change from +0.8001 to -0.1688 against Sacramento and +0.5978 to -0.1849 against Reno (frozen versus joint+clock; negative favors known). Median gaps do not show the same gain: against Sacramento -0.0434 becomes -0.0393, and against Reno -0.1911 becomes -0.0456. Joint fitting reduces severe scoring failures but weakens separation in many other cases. The model is neither uniformly better nor uniformly worse.

For the 35 newly evaluated scans at 100 Hz, the known-vs-Sacramento count increases from 21/35 to 27/35. Known-vs-Reno stays at 23/35. Both mean gaps improve, again influenced by severe failures in the frozen control.

## Large-error Reno cases

Joint+clock favors the known location over Reno in 5/6 cases at both noise settings, versus 4/6 for frozen IDs and 4/6 for joint IDs without clock. The remaining failure is 07:50, whose Reno estimate is 428.0 km wrong; both chains and both noise settings favor Reno there. This is a useful counterexample for further diagnosis.

The other five cases are 08:10 (675.8 km), 08:50 (123.5 km), 10:10 (214.8 km), 10:30 (688.0 km), and 12:50 (706.8 km). The pooled score improvement at 08:50 is inference-sensitive: at 100 Hz the chains pick different best locations, and at 200 Hz both individual chains favor Sacramento while their equally pooled per-track predictive mixture favors the reference. That does not establish reliable posterior mode weighting.

## Reliability prevents a deployment claim

- Different chains choose different best locations in 10/42 scans at 100 Hz and 3/42 at 200 Hz.
- At least one track/site has assignment total variation greater than 0.9 between chains in 28/42 and 18/42 scans respectively.
- The largest chain score spreads are 7.4765 and 1.8741 nats per evaluation block. Small score spread elsewhere does not certify assignment convergence.
- Historical timing prior mass outside ±120 seconds reaches 5.23%. The run conditions on finite support rather than resolving that tail.
- The block likelihood and GLRT uncertainty mapping remain uncalibrated; original train/evaluation masks overlap in time blocks and observations across tracks/receivers remain dependent.
- All locations and masks are retrospective. No location-error improvements were measured.

**Recommendation:** retain this as an experimental joint model. The next bounded work should improve posterior exploration (blocked/tempered assignment moves and convergence checks), then calibrate measurement dependence/noise and check timing-support convergence. Do not tune priors or aggressive track weights solely to make the known location win.

Full tables and scopes: `FULL_DS5_REPORT.md`. Per-scan scores and inference diagnostics: `full_summary.json`. Complete model outputs: `full_results.json`. Input accounting, return codes and per-scan logs: `full_run_plan.json`, `full_progress.json`, `full_logs/`. All 35 new return codes are zero; existing seven results were not overwritten.
