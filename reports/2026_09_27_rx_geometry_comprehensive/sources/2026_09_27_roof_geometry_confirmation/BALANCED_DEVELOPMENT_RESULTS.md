# Depth-balanced development result

All four runs completed in282–315seconds each. Hash verification and exact160-unique-point checks passed for every objective/prior. These are post-unblinding development results, not new confirmation. Models, observations, prior radii, grid levels and total budgets remain matched to the original topology experiment.

## Search effect, without adding geometry

| Scan | Prior | Original D km | Depth-balanced D km |
|---|---|---:|---:|
| b560 | Sacramento | 3.490 | 3.490 |
| b560 | Reno | 4.956 | 4.956 |
| f147 | Sacramento | 319.933 | 0.613 |
| f147 | Reno | 0.575 | 0.975 |
| 609d | Sacramento | 13.776 | 3.915 |
| 609d | Reno | 786.293 | 4.000 |
| 40eb | Sacramento | 228.119 | 228.119 |
| 40eb | Reno | 1.026 | 1.026 |

Changing only search allocation improves3 D cases, worsens1 and leaves4 unchanged. Thus the earlier large f147 geometry gain was not uniquely dependent on geometry: better Doppler-only coverage recovers the same0.613km point at the same160-point budget. The search does not eliminate every coverage failure (40eb Sacramento).

## Geometry effect under the new matched search

| Scan | Sacramento: D → joint km | Reno: D → joint km |
|---|---:|---:|
| b560 | 3.490 → 3.490 | 4.956 → 4.140 |
| f147 | 0.613 → 0.613 | 0.975 → 1.724 |
| 609d | 3.915 → 3.915 | 4.000 → 3.922 |
| 40eb | 228.119 → 19.831 | 1.026 → 1.500 |

Geometry improves3 cases, worsens2 and leaves3 unchanged. Its largest remaining gain is again search coverage, not a demonstration of fine resolution. The secondary RX-guided/D-selected method also gives19.831km on40eb Sacramento; it preserves D selections on all Reno cases except609d (4.000→3.922km).

The revised joint search improves3 cases relative to the original joint search, with5 unchanged. No prior uses another prior's fitted candidates or selected coordinates. Reference-centered diagnostic points were not supplied to this search.

## Interpretation

Depth balancing is a promising search repair worth independent validation. The evidence still does not establish consistently better fine-position accuracy from RX geometry. In particular, b560's frozen objective bias persists and 40eb's19.8km residual error is not high-resolution localization. Do not claim success from the smaller error averages alone.

Next evaluate the fixed depth-balanced policy on a disjoint, readiness-selected outcome-blind cohort, retaining D/joint/secondary comparisons and the predeclared dependence sensitivity. Separately investigate local score bias using calibration-only reception/association diagnostics; do not tune to the new cohort. All four recordings here are development data for that evaluation.

Machine-readable results: `balanced_development_distances.json`. Protocol: `BALANCED_DEVELOPMENT_PROTOCOL.md`.
