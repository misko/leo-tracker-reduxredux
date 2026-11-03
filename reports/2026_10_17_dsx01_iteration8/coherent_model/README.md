# Fixed-partition coherent density adapter — no fits

Eight component tests pass. The adapter changes the likelihood while retaining the complete existing joint-band physical state, calibration function, actual-RF orbit scaling, clock, timing gauge, q coordinates/budget, absolute band parameters, bounds/scales and every prior. No optimization, actual-source likelihood qualification, held scoring or performance comparison was run in this directory. The separate pilot qualifier owns any later real-data checks.

The imported [kernel](../coherent_density/kernel.py) is normalized for a **fixed supplied partition**. Its group prior is π₀=0.1 and πₛ=0.9 qₛ/Σq. A row's component density is `h_ns = .88*w_ns*wrappedGaussian + (1-.88*w_ns)*U`, with `U=1/ALIAS_HZ`; group density is `.1*U**n + sum_s π_s*product_n h_ns`. The whole-group clutter branch is retained. Point signal responsibilities include the within-component signal-versus-uniform posterior; a group's identity posterior alone is not a point signal posterior.

The automatic partition is chosen from TRAIN CFO, then frozen. This is a fixed-partition **working likelihood**. It does not model the probability of the linking-selection event and is not a globally normalized model of `y → chosen partition`, nor evidence for Bayes factors across grouping policies. Proper normalization for a supplied partition and the separate singleton forecast do not remove that limitation. No emitter-identity or localization claim follows from this component.

## Ports

`adapter.py` uses uniquely named module imports, without monkeypatching production or sealed model code.

- `make_context(original_shared_context, policy='independent'|'automatic', eta=.10, epsilon=.12)` appends the sealed joint-band state when needed and returns a new context. It also accepts this adapter's `joint.JointBandObjective` context. Existing vectors/nuisances are copied. Model scores only TRAIN observations. `full_model` uses singleton labels on all original metadata retained by the supplied context; it never builds tracks from held CFO. A truly TRAIN-only input contains only TRAIN rows, so unseen metadata must use the prediction port below.
- `CoherentBandObjective(joint_model, labels, eta=.10, epsilon=.12)` is the mathematical fixed-label adapter. The pilot should use the factory's two policies, never supplied DSX membership, target identities or selected windows. `evaluate_details` returns the existing objective/physical-gradient/nuisance-gradient/point-terms tuple and group diagnostics. Every q gradient chains the kernel's normalized-q derivative through the original hyperparameter Jacobian. Frequency and visibility derivatives both enter geometry/timing gradients.
- `predict_coherent(ctx, vector, nuisance, metadata)` is the existing complete joint calibration/orbit prediction transported through an explicit adapter. It ignores metadata CFO, does not construct labels and preserves original RF/time centers and all clock/band terms.
- `singleton_marginal(measured_hz, prediction_dict, eta=.10, epsilon=.12)` is evaluation-only. It uses `arange(N)` labels with the new density for every new/held point. Its per-row NLL is `terms.group_nll[terms.group_index]`. This singleton control **does not nest the original production shared density**. Original shared scoring, if desired for comparison, is a separate evaluation at the same predictions/q/visibility/125 Hz width.
- `classify(terms)` compares the maximum point signal responsibility with total point clutter, including whole-group and within-candidate uniform branches. It returns best index, associated flag and residual. These are model labels, not truth.
- `group_summary(model)` reports the partition size distribution, not a performance score.

There is no honest additive row-NLL decomposition of a multi-point group likelihood. Details expose group NLL/posteriors/index; `row_nll` is provided only when every group is a singleton. No equal division of group loss is presented as a point predictive loss.

## Automatic grouping authority and assumptions

The factory first applies the full-length boolean TRAIN mask and verifies scored/raw ordering. It uses the existing sealed `model_b.training_observations` and `build_tracklets`, with unchanged 450 Hz gate,45 s duration and24-point maximum. Every TRAIN row belongs to exactly one tracklet, so overlapping evidence is not counted twice. Both policies can share the identical physical seed and q state. No candidate/DSX/window/position labels enter grouping.

The old builder links raw carrier CFO in receiver/channel lanes, estimates a robust common drift, batches **exact** timestamps and infers revisit gaps from unique stamp differences. Microtimestamp jitter can fragment visits or affect cadence inference; no cadence fix or outcome-driven tuning was added here. The factory rejects multiple actual RF values within a TRAIN receiver/channel lane rather than silently link different RF settings. A future generic RF-splitting policy would be a separately tested change. Within a linked group the same latent candidate is assumed possible over its finite duration; point clutter allows isolated contamination, but the linking algorithm's mistakes are not modeled as an extra selection likelihood.

## Validation and boundaries

Eight tests cover complete prediction/prior equality with the joint-band state; finite differences of all physical, clock, q and band coordinates for singleton/grouped likelihoods in both c arms; total-timing gauge gradients; arbitrary singleton-label equivalence with the new point forecast; explicit non-equivalence to production shared density; automatic TRAIN grouping invariance to excluded CFO/margins; multi-RF rejection and source immutability; CFO-blind metadata prediction; and point classification when group identity probability is high but all row mass is clutter. The absolute50000 Hz band prior is retained exactly once. Existing strict bounds/priors are not changed.

Tests ran with the pinned scientific environment, one BLAS thread, and synthetic geometry kernels only. Those local test patches are not implementation hooks. No real fit, RF, station/reference read, production change or modification to previous sealed code occurred. The manifest binds adapter/tests, the sealed kernel and the two sealed imported model/grouping authorities.
