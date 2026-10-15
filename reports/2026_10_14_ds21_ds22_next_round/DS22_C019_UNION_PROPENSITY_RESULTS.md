# DS22-019: expanded-bank native propensity profile/release results

The 67-satellite no-clock propensity model substantially improves training likelihood but retains the distant selected basin. Its configured-reference distance changes from 142.976656 to 142.648857 km. The common-clock propensity result is unavailable: both fixed profiles reported solver success but failed the unchanged strict KKT gate, so their free releases were correctly skipped. This is not evidence that the common-clock propensity model has poor position accuracy; it has no accepted estimate in this experiment.

| Native model | Conditional source distance km | Propensity selected distance km | Conditional objective | Propensity objective | Conditional NLL | Propensity NLL |
|---|---:|---:|---:|---:|---:|---:|
| Without common clock | 142.976656 | 142.648857 | 42269.512217 | 40012.072991 | 41875.801489 | 39595.500475 |
| With common clock | 143.256619 | unavailable | 41853.246701 | unavailable | 41398.063189 | unavailable |

All distances were computed only after the complete experiment seal and are against the configured, unconfirmed station reference. No verified accuracy, held prediction or model promotion is claimed. No matched expanded-model half-position fits were run.

Four complete source states were prespecified by minimum accepted training objective within each model × original/coarse group, using the frozen 67-candidate union. Each fixed profile started from that source's complete physical/calibration/timing state plus zero propensity. Original controls kept their own 25 km disks; coarse sources kept their original grid-derived 141.421356 km disks. All four profiles completed before any release. Only accepted profiles supplied a complete-state release. Every call used fitted-c, 60 seconds, 600 iterations and strict full KKT ≤0.001; optimizer iterations are not an objective-evaluation cap.

| Call | Training objective | KKT | Solver success | Strict accepted | Fit seconds | Evaluations |
|---|---:|---:|---|---|---:|---:|
| No-clock original0 fixed | 40013.409557 | 0.000125375 | yes | yes | 56.177 | 753 |
| No-clock coarse16 fixed | 40540.458281 | 0.000604525 | yes | yes | 40.132 | 532 |
| Clock original0 fixed | 39651.359453 | 0.002337809 | yes | no | 33.019 | 433 |
| Clock coarse12 fixed | 40785.631516 | 0.007060624 | yes | no | 45.172 | 589 |
| No-clock original0 free | 40012.072991 | 0.000979316 | yes | yes | 26.174 | 319 |
| No-clock coarse16 free | 40532.121737 | 0.000195745 | yes | yes | 28.821 | 376 |

Thus six actual fits ran, four were strictly accepted, and two clock releases have explicit zero-call skip receipts. Both rejected clock fits stopped before the wall deadline; simply allocating more time would not establish a remedy. No failed endpoint was retried, no acceptance threshold changed, and the clock profiles cannot enter the free-position selector.

The accepted no-clock original-source release beats the accepted coarse-source release by 520.048747 objective units and is selected entirely on training objective. It also improves upon its zero-tail feasible bound by 2257.439226 objective units. Zero-tail full expanded KKT was nonstationary for all four sources, so those states were retained as feasible bounds rather than silently accepted expanded incumbents. Better training likelihood did not produce useful localization here. Only two training-selected sources per model were profiled; this is not an exhaustive propensity search over all twenty-two coverage starts.

The wrapper qualification and separate coarse16 timing-margin recovery are documented in `DS22_C019_UNION_PROPENSITY_QUALIFICATION.md`. The original zero-objective admission failure, three original successful qualifiers and one explicit recovered qualifier remain preserved. No original cohort outcome was changed. The fixed-profile wave took104.561 seconds and the release/skip wave77.751 seconds, including preparation and independent post-optimizer audits.

## Authority

- Original qualification `3d001e27f`; recovery/profile source `633f7cd68`; evaluator/source binding `4d8a44dfd`.
- Namespace: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-c019-union-propensity-profiles-v1`.
- Protocol SHA256: `5cf38bb7edd294745d9611fefa6b2d86b4bd4524472f2395af8f46f5bd1113ec`.
- Terminal SHA256: `fdf44d9179e89c1777879a5fca5da86869495529e786adfc9f000a73dfd3130e`.
- Seal SHA256: `2965593c4852938306e9504f712e3c208237bdf71ce980151f3e808b477ce088`.
- Post-seal configured comparison: adjacent `ds22-c019-union-propensity-comparison-v1/report.json`.
- Held and locked data were untouched. Fold predictive controls would be required before interpreting in-sample propensity gains as generalization.
