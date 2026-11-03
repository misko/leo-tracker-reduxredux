# Frozen pooled associations suppress displaced fits but lose held prediction

Freezing candidate/background probabilities from the pooled N24 training fit reduces reference distance in **all 18 eight-scan panels**, increasing the number below 1 km from **5 to 8**. Both highlighted association-responsive failures shrink substantially. However, original-model held prediction improves in only 9/18 panels and loses 214.11 nats in the descriptive sum. Every new panel estimate remains farther from the reference than its own N24 donor. This diagnostic is not a deployable accuracy improvement.

| Panel | Original reference distance (m) | Frozen-probability fit (m) | Original-model held change (nats) |
|---|---:|---:|---:|
| DS8 balanced-2 | 2,212.0 | 558.4 | −75.42 |
| DS9 contiguous late | 3,897.4 | 978.8 | −89.76 |

[All 18 results](table.md) · [Full-precision summary](summary.json) · [Frozen protocol](PROTOCOL.md)

## Matched evaluation

| Panel family | Fits | Closer to reference | Below 1 km before → after | Held improvements | Summed held change (nats) |
|---|---:|---:|---:|---:|---:|
| Contiguous windows | 9 | 9 | 2 → 3 | 3 | −108.34 |
| Interleaved balanced sets | 9 | 9 | 3 → 5 | 6 | −105.77 |

The two families reuse the same 72 scans across DS7–DS9. Their combined totals are descriptive, not independent replications or calibrated significance evidence. Held scores concern the existing within-track held observations, not completely excluded scans. Both donor and panel fitting use training observations only.

## What changed

Freeze the full soft posterior over retained satellite candidates and the unassociated-trend component at each scan's N24 donor location/timing. Optimize the expected component training log likelihood plus fixed donor entropy. This is a tangent lower bound of the original mixture likelihood; it is not itself a normalized observation density.

For each panel, use two starts: its existing selected fit and the donor restricted to its eight scans. Select by qualified surrogate training score. Both starts qualified in every panel (36/36). No starts used the geographic reference. All evaluated visible candidate supports remained unchanged; no failed-support fallback was needed.

Evaluate the resulting parameters through the original mixture's ordinary training-conditioned held likelihood. This deliberately preserves the measurement model used for the comparison. It does not claim held performance of a separate frozen-probability density. Training likelihood under that original model decreases in all 18 panels, as expected when adding this restriction to previously optimized fits.

## Interpretation and next decision

The experiment confirms that constraining soft association can suppress the two previously diagnosed displacements. It does **not** show that the pooled assignments identify true satellites or that freezing them improves predictive validity. The donor includes all 24 scans, including the evaluated panel, and already has better reference agreement than every new estimate. The gain may reflect useful donor information or attraction toward a better pooled solution, rather than a transferable association rule.

Do not promote this restriction into the baseline. The next necessary test is a donor formed from scans excluded from the target panel, with target timing and candidate probabilities handled using training evidence only. Compare against direct use of the donor position and the target's unconstrained fit. This controls whether frozen association adds value beyond inheriting a location estimate. Retain geographic and predictive outcomes separately; do not tune the restriction on the exposed reference.

## Numerical evidence

Two synthetic tests passed: tangency/lower-bound behavior and finite-difference gradient agreement. Across all real panels, donor score equality error is at most 1.46e-10 nats and gradient disagreement at most 1.95e-12. The largest optimizer finite-difference audit error is 5.99e-6, below the inherited 0.02 gate. Lower-bound checks pass at the original panel and new selected endpoints. Dataset processes finished in 48–56 seconds under 300-second caps, with no retries.

The [model](frozen_model.py), [runner](run.py), [launcher](launch.py), [source/code hashes](manifest.json), raw per-panel outputs and process receipts are retained. [summarize.py](summarize.py) computes reference distances after fit selection. Exclusive output creation prevents overwriting completed runs.

The reference coordinate has unquantified uncertainty; candidate banks remain site-conditioned; all panels have prior research exposure. No new RF collection, production changes or remote publication occurred.
