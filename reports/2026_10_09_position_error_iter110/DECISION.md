# Persistence pilot does not pass its frozen screening rule

All12 selected consumed recordings completed, with all48 raw fits independently qualified and no fallback or input failure. Fixed rho0.5 gives a modest fitted-c mean reduction of3.07%, short of the predeclared5%, while the fitted median worsens. Retain production B7; this is not evidence for deployment or the0.4km objective.

| Arm | rho0 mean / median km | rho0.5 mean / median km | rho0 / rho0.5 worst km | Improved / regressed |
|---|---|---|---|---|
| fitted-c | 1.117359 / 0.905836 | 1.083074 / 0.914724 | 3.389263 / 3.182841 | 6 / 6 |
| c=0 | 1.280581 / 0.826722 | 1.253832 / 0.907871 | 4.193248 / 3.683027 | 5 / 7 |

No paired regression exceeds1km; the largest regression is0.046669km fitted-c and0.266908km c=0. The c=0 same-start rho0 control differs from archived B7 on one member by0.295352km; archive comparison remains separate. Both experimental arms share fitted-derived starts, observations, banks, priors and budgets. No reference error selected a start, model or winner.

Frequency effects do not establish position benefit. Median posterior RMS is59.940→59.231Hz fitted-c and107.641→108.083Hz c=0; mean RMS worsens in both arms. Rho-specific sequence scores have different likelihoods and are not operational winner criteria.

Maximum fit elapsed time is22.159s, within the90s soft per-fit limit. Sum of fit costs is391.246s, reconstruction158.162s, and total recording costs552.305s. These sums are not concurrent wall time; peak recording memory was not measured. The plot was visually checked for readable matched-arm cumulative and paired errors.

[Complete report and visualization](RESULTS.md), [all statuses, gates and metrics](summary.json), and [report/raw receipt integrity](report-integrity.json) preserve membership and paired regressions. This12-member consumed diagnostic does not update the full148/193 mean, establish independent validation, or authorize a broader sweep.
