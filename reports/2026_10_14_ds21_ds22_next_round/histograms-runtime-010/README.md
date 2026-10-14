# DS21 matched histogram update: 16 complete pairs

Both arms use CH1–8 with fitted c. Before means original discovery; after means expanded discovery. Later experimental clock, solver and disk-release changes are excluded. These development results do not establish performance on the locked cohort.

| Model | Paired median before, km | Paired median after, km |
|---|---:|---:|
| A | 2.635667 | 2.581679 |
| B | 5.458523 | 2.514876 |
| C | 3.138465 | 3.269016 |

The plot uses the same 16 cases with all six estimates. There are 17 sealed before/after cases, but DS21-035 has no accepted before-C estimate and is excluded from all plotted arms. It remains in the CSV and summary: before A/B errors are 24.604555/6.289808 km; after A/B/C errors are 188.806592/96.957197/177.317260 km. This severe regression must not be hidden by the complete-case histogram. It is the new worst after case across all three models.

Seventeen after matrices are complete out of 34 eligible development cases. Before has 21 completed matrices, with one unavailable C estimate. The summary statistics use all available estimates in each arm and therefore differ from the paired medians above. Pending cases are not failures, and no unavailable error is assigned a numeric value.

Generated using tools/ds21_runtime_histograms.py with every completed model-a-pipeline runtime receipt. The collector verifies original scientific parents, all twelve unit bindings, fitted-c settings and matched budgets. Source bindings and fixed cohort membership are recorded in summary.json. Histogram bins are categorical intervals with unequal numerical widths, labelled explicitly.

Files: histogram.png, histogram.svg, errors.csv, data.json and summary.json. The 0.5 km median target remains unmet.
