# Matched native-clock channel views on DS22-001

The combined fit remains worse than both channel halves in this controlled native-clock model comparison. All nine prescribed fits passed the unchanged independent stationary acceptance rule. Distances below use the existing configured station coordinate, whose continuity with DS22 remains unconfirmed; they are not verified ground-truth accuracy.

| Scored channels | Selected training seed | Position distance (km) | Training NLL | Windows |
| --- | --- | ---: | ---: | ---: |
| CH1–8 | B-profile-release | 5.582157 | 39721.093124 | 3229 |
| CH1–4 | low-anchor | 4.381020 | 21337.218785 | 1811 |
| CH5–8 | B-profile-release | 2.779966 | 17266.458897 | 1418 |

Each view received the same three previously accepted, full-training-derived states: the profile-then-release state transported from B, and the native-clock low- and high-anchor releases. Every seed retained its original 25 km search disk across views. Each fit had 20 seconds and at most 600 actual objective evaluations, with fitted `c`, identical calibration and timing priors, and unchanged strict KKT acceptance. Selection minimized training objective among accepted fits within each view; no reference or held observations selected a seed.

The likelihood mask preserves the complete observation frame, candidate bank, RF/time centering, receiver-clock nodes, group calibration contrasts, and prior precision. Only the scored observation rows change. Actual qualification verified exact all-channel objective/gradient replay, the sum of half-band NLLs, and feasibility of each unchanged seed. Four component tests cover masking and reject unsupported accelerated subclasses. Qualification used 12 objective evaluations and no fits. All nine subsequent fits were stationary without the optional gradient finish.

This is a conditional channel ablation using shared discovery and full-band training-derived starts. It is not independent half-only discovery, and its halves should not be conflated with historical C halves that lacked the common receiver-clock model. Objectives and total NLLs across differing observation counts are not direct model rankings.

The earlier profile/release decomposition found a large decrease in common-clock penalty during movement away from the B geography. A separate, prespecified sensitivity experiment will double only the common-clock prior standard deviation, retaining these exact seeds, disks, views and fit budgets. It tests that penalty tradeoff; it does not select a hyperparameter by position error or establish that the prior is causally wrong.

Source: `c80167512` pilot, `28df75100` view robustness, `8cf4c93df` evaluator. Evidence: `local/ds22-native-view-pilot-v2` and `local/ds22-native-view-comparison-v1`. An earlier freeze attempt failed on a metadata-envelope lookup before creating an experiment namespace or executing scientific work; the corrected loader has a regression test. No failed numerical call was retried.
