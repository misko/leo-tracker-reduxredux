# Fresh roof confirmation: geometry does not yet establish better resolution

All four topology-amended primary searches and all four predeclared reciprocal-pair sensitivity searches completed successfully. Each of their four arms (two objectives × two independent priors) evaluated exactly160 points. Saved implementation hashes match the current files. Both whole-cohort reporters passed their input/model bindings before distance unblinding. No failed scan was replaced.

Distances are kilometers from the operator-provided roof reference, not surveyed ground truth. The comparator is the matched experimental Doppler model, not production.

| Scan | Prior | Doppler | Joint RX geometry | RX-guided, Doppler-selected |
|---|---|---:|---:|---:|
| b5604c3d838fa7ed | Sacramento | 3.490 | 3.490 | 3.490 |
| b5604c3d838fa7ed | Reno | 4.956 | 4.140 | 4.956 |
| f147dd8a5bc99346 | Sacramento | 319.933 | 0.613 | 0.613 |
| f147dd8a5bc99346 | Reno | 0.575 | 1.724 | 0.575 |
| 609d7a8d9861f3db | Sacramento | 13.776 | 13.776 | 13.776 |
| 609d7a8d9861f3db | Reno | 786.293 | 788.502 | 786.293 |
| 40ebc07665464c7d | Sacramento | 228.119 | 252.215 | 252.215 |
| 40ebc07665464c7d | Reno | 1.026 | 1.500 | 1.026 |

Primary joint scoring improves2, worsens4, and leaves2 unchanged. Sacramento mean error improves141.329→67.523km, dominated by one recovered region; Reno mean worsens198.213→198.967km. Sacramento median improves120.947→8.633km; Reno median changes2.991→2.932km. The median alone masks three Reno regressions and one remaining catastrophic error.

The frozen secondary improves1, worsens1, and leaves6 unchanged. All four Reno outputs match Doppler-only. It avoids the joint score's fine-position regressions but loses its one Reno gain. Neither method establishes reliable finer resolution.

## Dependence sensitivity

Keeping only one reception row per matched physical pair removes30,28,23,18 rows in the displayed scan order. All primary and secondary selected coordinates remain exactly unchanged. Thus these particular selections are insensitive to reciprocal-pair duplication. This does not establish independence of all remaining observations or validate posterior uncertainty.

## Interpretation and next diagnostic

The large Sacramento gain is a finite-budget search-coverage improvement: Doppler ranking over the combined diagnostic inventory also selects0.613km. That inventory is not a budget-matched estimator. In contrast, the poor Reno609d solution persists with and without geometry. Priors and candidate assignments remain independent; a successful Sacramento location cannot be supplied to its Reno evaluation.

The next useful experiment must separate inadequate search coverage from misranked locations, and directional antenna information from receiver-specific nuisance effects. On these now-unblinded recordings, diagnose frozen-score profiles and independent-prior coverage; compare geometry against a reception model without directional terms, not only against no reception evidence. Any adapted search or model then needs a new outcome-blind confirmation cohort. These four recordings must not be reused as untouched confirmation for a tuned method.

No claim of improved production performance, calibrated uncertainty, surveyed precision, or goal completion is supported. No new RF collection or production/source-data changes were made.

Artifacts: `topology_distance_results.json`, `topology_dedup_distance_results.json`, their bound `topology[-dedup]-search-*.json` files, `AMENDMENT_SOURCE_TOPOLOGY.md`, and `SECONDARY_PROTOCOL.md`.
