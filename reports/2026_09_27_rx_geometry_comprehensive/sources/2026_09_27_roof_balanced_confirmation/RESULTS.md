# Second outcome-blind roof confirmation

All four primary and four duplicate-pair sensitivity runs completed successfully in610–683seconds each. Both whole-cohort reporters verified frozen input/model/code bindings and exactly160 unique evaluated points per objective/prior before reading reference positions. No recording was replaced, no parameter was changed, and priors remained independent.

Distances are kilometers to the operator-supplied roof coordinate, not surveyed GPS truth. Each pair is experimental Doppler-only → joint RX geometry under the same fixed depth-balanced search.

| Scan | Sacramento km | Reno km |
|---|---:|---:|
| 339af454a2aab2f4 | 1.958 → 1.958 | 2.580 → 1.896 |
| 53ce822d78d476ba | 5.040 → 5.800 | 5.701 → 5.701 |
| e76c229e9dc498b3 | 3.605 → 3.605 | 6.549 → 5.520 |
| c9db23377d1194dd | 6.123 → 6.123 | 6.128 → 6.128 |

Primary geometry improves2 cases, worsens1, leaves5 unchanged. Reno mean improves5.239→4.811km (about8.2%); Sacramento mean worsens4.182→4.372km (about4.5%). Overall mean improves4.711→4.592km, while overall median worsens5.371→5.611km. These mixed statistics should be presented together, not selected to suggest a uniform gain. The eight prior cases are not eight independent recordings.

## Frozen secondary

Selecting the lowest Doppler score only among the geometry search's own evaluated points improves e76c Reno6.549→5.520km and leaves the other7 cases unchanged. Its overall mean changes4.711→4.582km. This preserves one coverage benefit and avoids the53ce Sacramento regression, but loses the339af Reno joint-ranking gain. One improved case in four recordings is not a reliable population-level resolution claim.

## Dependence and scope

The predeclared sensitivity keeps one reception contribution per matched physical RX pair. Every primary selected coordinate is exactly unchanged, and the reported secondary distances also match. This rules out sensitivity of these particular selections to reciprocal duplication; it does not make temporal observations independent or calibrate posterior uncertainty.

All locations are within6.55km in this cohort even without geometry. That is consistent with useful broad search coverage here, but it cannot isolate a search-policy benefit because the old search policy was not run on this cohort. The causal geometry comparison is matched and fixed-budget. The primary model still does not establish consistently better fine localization across both priors; no production superiority, survey accuracy, confidence-interval coverage or general tracking-resolution guarantee is claimed.

Calibration uses only the original six filtered scans. The5MHz e76c recording uses a sample-rate level not seen in calibration and therefore reference-level encoding; report that limitation without assigning causality to it. Receiver pose and antenna response remain approximate.

The goal is not complete. The next scientific question is whether the small local directional corrections survive an equal-coordinate fine-resolution comparison and better-calibrated antenna/association nuisance modeling. Do not tune using these outcomes and continue to describe this cohort as untouched confirmation.

Artifacts: `distance_results.json`, `dedup-distance_results.json`, `contract.json`, `PROTOCOL.md`, and bound `search-*.json` / `dedup-search-*.json` outputs.
