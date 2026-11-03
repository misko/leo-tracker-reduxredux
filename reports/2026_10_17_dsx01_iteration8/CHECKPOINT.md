# DSX01 iteration8 — exact coherence, not a new recovery claim

The previous goal turn made progress: four matched initialization fits, exact saved-source replay and an all-five identifiability audit completed and changed the next research decision. The 15-window recovery objective remains active. Existing complete development results and all negative transfer evidence remain unchanged.

## Working hypothesis

Test automatic shared track identity inside the fitted working likelihood, rather than restoring a trajectory proposal to an independent-point objective. Existing automatic tracklets and earlier manually grouped fits are references, not newly discovered methods. This iteration adds explicit point and group clutter to a normalized fixed-partition kernel and uses exact orbital/calibration derivatives throughout.

The partition is selected from TRAIN CFO and then frozen. Normalization is conditional on the supplied partition; the acquisition/linking selection event is not modeled. No marginal likelihood or Bayes-factor claim is justified. Future-point predictions are normalized singleton marginals and never use held CFO to construct groups. Model identities remain unverified.

## Current components and gate

- `coherent_density/`: sealed kernel and nine component tests covering normalization, explicit latent enumeration, gradients, periodic alias behavior, clutter, partition invariants and stability. Kernel SHA256 `fe80d9b574c30108d8317429db85d69aa467e3410b016eb3fdd72e2cfc3e2bc1`.
- `coherent_model/`: complete joint-band state adapter and eight owned tests are sealed. Independent review passed the same eight adapter and four pilot-port tests. Independent and automatic policies share parameter layout, full physical/calibration/clock/timing/q/band priors and bounds. Full-model prediction is always singleton. Automatic segmentation uses the previous 450 Hz /45 s /24-point defaults and rejects multi-RF receiver/channel lanes. Adapter SHA256 `4564048e54d83a0f73617bd4fc3ce662617e6557e9c00321778ca223dbec7de7`.
- `coherent_pilot/`: complete and sealed (47 files). Actual qualification passed 930 objective calls and eight metadata predictors before root authorized four fits. All four outcomes and then all four metadata-only predictions sealed before held scoring. Final seal SHA256 `0df1175aea92570f4f84a26ec4fc10abb363013c353fdffbcff1688445c24186`.

Use only the existing genuinely TRAIN-derived S03 blocked 2,073-row /45-ID context. Four eventual outcomes compare independent/automatic times fitted-c/conditional c=0, same complete training seed, same causal ephemeris bank, free receiver bands and 1,000-call/120 s allowances. All four outcomes must seal, then all four metadata-only predictions must seal, before evaluating 1,909 held rows, six boundary rows and the fixed 80 requested held observations. Other sources/windows remain untested until the gate is passed. No manual DSX membership, station coordinates or omitted candidate hypotheses enter fitting.

Before pilot outcomes, root specified the gate for an all-five development expansion: both fitted-c endpoints strict; automatic policy's total held singleton NLL lower and at least four of seven excluded 20 s blocks improved; original shared-density held classification count and 80-point requested count both nondecreasing against the independent control. Retained-intersection RMS, native posterior classification and c0 sensitivity remain visible separately. This is a broadening gate, not production promotion or proof of geographic accuracy. No held hyperparameter tuning, threshold relaxation, per-block winners or repeated fits to pass the gate.

## Completed pilot: negative expansion gate

Fitted-c independent versus coherent held singleton NLL was23146.608 versus23227.178 (80.570 worse), with only two of seven excluded blocks improving. Original shared-classifier coverage was806 versus803/1909; requested held coverage73 versus70/80. Configured-reference distance was6.847 versus7.767km. Independent fitted-c passed strict KKT; coherent fitted-c did not (.001956 versus the unchanged .001 limit). All five expansion conditions failed. The coherent model will not expand to all five sources.

Conditional c0 results also remain visible: held singleton NLL24056.237 versus23461.146, original classifier670 versus812/1909, requested53 versus47/80. Independent c0 failed strict KKT; coherent c0 passed. All four raw endpoints remain published locally, without retries or acceptance filtering. Total inference used1721 objectives plus four independent terminal audits.

The sealed root-owned `original_anchor/` audit replays the original cold density, assignments, identities and residuals exactly, and aligns all original observation IDs through the frozen source order and timestamps. Against original795/1909 and66/80, independent fitted-c gained46 and lost35 held assignments; coherent gained59 and lost51. Requested independent gained8/lost1; coherent gained5/lost1. These are descriptive anchors: the new fits also free bands and add optimization in a broader research domain, so they do not isolate a density effect.

## Frame/CFO audit and next bounded control

`frame_cfo_relation/v2/` corrects circular CFO representation while preserving the v1 failure evidence. On208 excluded points, pooled constant-CFO baseline RMSE was .762944ppm, versus .967482 for fixed positive unit phase-rate scaling and1.325948 for negative scaling. Nevertheless positive scaling improved20/21 informative quadratic-phase segments and beat all32 within-segment held-CFO permutations. This supports a local empirical relation, not a universal clock constraint, verified satellite identity, or independent range observable. The learned phase-rate slope is equivalent to an ordinary time trend in these quadratic segments.

Iteration9 proposes exactly two matched legacy shared-density free-band controls, fitted-c and conditional c0, reusing the immutable independent new-point outcomes. Both density families are already normalized: signal/clutter weighting, odds and visibility dependence differ, so this tests the density family, not normalization alone. Independent review passed six component tests. Root must inspect actual zero-fit qualification before authorizing fits. S03 has already been explored; this is a posthoc hypothesis test, not unseen confirmation. No coherent refit or automatic all-five expansion is authorized.

The 15-window goal remains active. Success still requires a single position-independent method improving the full cohort with truthful whole-scan support and localization reporting, followed by DS21/DS22 transfer checks. No production, remote push, RF collection or sealed-evidence rewrite occurs.
