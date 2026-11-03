# Disjoint-panel disagreement exceeds near-best optimizer variation

The saved six-start fits do not explain the kilometre-scale disagreement between scan sets through their available near-best alternatives. Across 18 fits, the largest diameter of qualified solutions within one training nat of the best is **34.71 m**. Across disjoint panels, selected-point separations are **893–4,453 m** for contiguous windows and **1,108–3,273 m** for interleaved balanced sets. Comparing the closest near-best alternatives leaves these separations unchanged at the displayed 0.1 m precision.

This shifts attention toward observation-dependent model error and association/timing behavior across windows. It does not prove a particular physical cause or exclude undiscovered modes: only the six saved starts are examined, and the candidate banks remain site-conditioned.

[All pair comparisons](table.md) · [Full results and source hashes](results.json) · [Frozen protocol](PROTOCOL.md)

## Cross-panel agreement does not certify accuracy

Before examining pair outcomes, freeze a strict 1 km selected-location separation gate and evaluate the arithmetic geographic midpoint as a descriptive common-site candidate.

| Family | Scan-disjoint pairs | Passing agreement gate | Passing midpoint below 1 km reference distance | Passing midpoint at least 1 km |
|---|---:|---:|---:|---:|
| Contiguous windows | 9 | 1 | 0 | 1 |
| Interleaved balanced sets | 9 | 0 | 0 | 0 |

The only accepted pair is DS7 middle/late: its selected points are 892.9 m apart, while its midpoint is 1,603.2 m from the operator reference. The rule therefore has 1/18 acceptance and no accepted midpoint below 1 km. Rejected pairs include closer-reference midpoints; no pair or threshold is chosen after observing those distances.

Each pair uses 16 distinct scans, but pairs reuse panels and the two families cover the same 24-scan pool per dataset. These are not 18 independent validation trials. Balanced sets are interleaved in time and must not be described as separate temporal blocks. Midpoint calculations are descriptive, not new joint likelihood fits.

## Optimization evidence and limitations

The audit reads three cold starts and three timing-grid starts per panel. Of 108 saved starts, 107 qualified; the failed start remains in source evidence and is excluded from mode calculations. The largest diameter over **all** qualified starts is 2,299.2 m, demonstrating that inferior local solutions can differ substantially. The much smaller near-best diameter concerns only alternatives within one training nat of the best.

For every panel, the saved selected score matches the best qualified score within 1e-6. Membership checks establish that the three panels within each family are pairwise disjoint, comprise exactly 24 scans, and cover the same pool as the other family. No new optimization was run. Local E/N separation and spherical reference distance are distinct metrics, explicitly preserved in the result fields.

The one-nat cutoff is a diagnostic definition, not a posterior credible region or proof that all plausible modes have been found. The geographic reference has unknown uncertainty and has been repeatedly exposed. The result cannot establish independent absolute accuracy.

## Implication for further model work

Neither local sandwich uncertainty nor cross-panel agreement has demonstrated a reliable subkilometre gate. Continue retaining separate window solutions rather than summarizing them as a tightly localized confidence ellipse. A useful next model experiment must test a physical or observation-level mechanism behind changing location estimates, with matched observations and held prediction alongside reference distance. Merely adding optimizer starts or tuning an agreement threshold is not supported by this evidence as the primary next step.

The existing pooled N24 result remains a working baseline; averaging opposite panel errors can improve reference agreement without showing that either panel's measurement model is correct. Any aggregation improvement must therefore retain the separate-window failure evidence.

## Reproduction

Run `python3 reports/2026_09_29_temporal_modes/study.py` from the repository root in a fresh output directory. The runner refuses to overwrite `results.json`, records hashes of all 36 source JSON files, verifies membership and training-score selection, and produces the pair table. No radio collection, production changes or remote publication occurred.
