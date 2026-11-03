# Joint fitting beats frozen association geographically at equal data budget

Ordinary joint fitting of the same 16 donor-plus-target scans is closer to the operator reference than constrained refinement in **all nine pairs**. Seven joint fits are below 1 km, versus two constrained fits. However, the joint estimates lose target-held likelihood in every comparison. The geographic result favors pooling; the predictive score favors target-specific adaptation. Neither metric can substitute for the other.

| Dataset | Donor + target scans | Joint16 reference distance (m) | Frozen-association distance (m) |
|---|---|---:|---:|
| DS7 | early + middle | 643.8 | 1,029.7 |
| DS7 | early + late | 176.2 | 1,665.1 |
| DS7 | middle + late | 1,727.7 | 1,950.8 |
| DS8 | early + middle | 1,091.7 | 2,064.4 |
| DS8 | early + late | 301.9 | 1,544.2 |
| DS8 | middle + late | 281.2 | 1,495.5 |
| DS9 | early + middle | 382.4 | 593.5 |
| DS9 | early + late | 753.6 | 1,183.9 |
| DS9 | middle + late | 184.1 | 640.0 |

[Full table including target prediction](table.md) · [Full-precision results](summary.json) · [Frozen protocol](PROTOCOL.md)

## Why the control matters

The preceding constrained method used eight earlier donor scans to establish a location, then eight target scans to fit target timings, freeze soft association and refine location. Its final fit used eight scans, but the method had access to 16. The present control gives the ordinary q=0.2 mixture exactly those same 16 scans and fits one position with independent scan timings. No membership is added or removed.

Three early+middle fits are reused from the prior cumulative16 experiment after exact ordered-session and source-score replay checks. Six other pairs are newly fitted with the established six-start protocol. All 36 new starts qualify; all nine selected joint fits qualify. Selection uses training likelihood only, never held likelihood or reference distance.

The result does not support freezing association as the preferred geographic estimator when ordinary joint fitting of all available measurements is feasible. It does support continued use of joint pooling as the geographic baseline. Two of nine joint fits remain above 1 km, so it is not a reliable subkilometre solution across windows.

## Predictive disagreement

On exactly the target window's held observations, joint fits lose against constrained refinement in 9/9 pairs, by a descriptive sum of **319.16 nats**. Against target-only fitting, joint fitting wins only 1/9 and loses **560.99 nats** in the sum. Targets reuse late windows across donor pairs, so sums are not independent validation statistics.

These are original-model training-conditioned held contrasts within the target recordings, not wholly excluded scans. Joint fitting trades target-specific residual agreement for a shared location across donor and target. The fact that this improves reference distance consistently while hurting held likelihood shows that the existing predictive metric is not an established accuracy-selection criterion for these alternatives. It does not prove why: shared model mismatch, target-specific association/timing response and reference-conditioning effects remain possible.

Consequently, selecting the method with the best held score would choose the geographically worse arm in every joint-versus-constrained pair here. Preserve both metrics rather than reporting either as a general improvement.

## Scientific scope

All three window pairs are evaluated per dataset. Within a pair, donor and target scans are disjoint; pairs overlap each other and come from the same sparse 24-scan pools. These are nine matched comparisons, not nine independent blind trials. No pair was chosen after its geographic result. Geographic distances use the previously exposed operator coordinate with unquantified uncertainty, and the candidate banks remain site-conditioned. The configured center already has 809 m reference distance.

The next model work should address the mismatch between a physically shared location and window-specific residual preferences, retaining ordinary pooling as a mandatory equal-data control. Improving conditional held score alone is insufficient evidence for progress toward absolute subkilometre accuracy. Freezing labels or increasing association rigidity is not supported as the primary geographic method by this comparison.

## Validation and artifacts

All reused fits pass score replay at their exact ordered membership. New timing-grid seeds pass scalar replay; new source fits pass optimizer, boundary and finite-difference gradient gates. Target-only training and held scores replay the previous comparison within 1e-7, ensuring matched target evaluation. No retries or numerical failures occurred. Dataset subprocesses completed in 138–183 seconds under their 300-second caps.

[run.py](run.py), [launch.py](launch.py), [source/code hashes](manifest.json), all starts and per-pair outputs, process receipts, and [summarize.py](summarize.py) are retained. The summary verifies frozen hashes and evaluates reference distances after fit selection. Outputs use exclusive creation to avoid overwriting prior evidence.

No RF collection, production modifications, golden-fixture changes or remote publication occurred.
