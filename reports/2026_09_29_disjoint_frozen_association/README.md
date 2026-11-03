# Frozen-association refinement with earlier, disjoint donors

Using only earlier scans to supply the donor position, constrained target refinement reduces reference distance in **all nine comparisons** against the target-only fit. It improves held prediction against direct donor-position use in all nine, but against the target-only fit in only three. Only two constrained estimates fall below 1 km. The transferable effect merits study; it is not a reliable subkilometre method.

| Comparison | Geographic improvements | Held-prediction improvements | Descriptive summed held change |
|---|---:|---:|---:|
| Constrained refinement versus target-only fit | 9/9 | 3/9 | −241.83 nats |
| Constrained refinement versus direct donor position | 5/9 | 9/9 | +1,292.31 nats |

[All nine comparisons](table.md) · [Full-precision summary](summary.json) · [Frozen protocol](PROTOCOL.md)

The target-only arm is below 1 km in 1/9 comparison rows; direct donor use in 3/9; constrained refinement in 2/9. These rows reuse target windows, so they are not nine independent localization trials. In particular, each late window is evaluated with two different donors. The sums above describe those comparisons, not independent evidence or calibrated significance.

## Concrete outcomes

- DS7 early→middle moves from 1,201.8 m target distance to 1,029.7 m, despite the earlier donor itself being 2,286.0 m away. This improvement cannot be described merely as copying a better donor coordinate.
- DS9 early→late reduces the target's 3,897.4 m distance to 1,183.9 m, still outside 1 km and worse geographically than directly using the 639.5 m donor.
- DS9 middle→late reduces the same target to 640.0 m, closer than both target and 841.8 m donor. It loses 84.5 held nats versus the target-only fit while gaining 33.9 versus direct donor-position use.

Different donors can therefore produce materially different target refinements. No donor is chosen after seeing reference or held outcomes: all early→middle, early→late and middle→late pairs are reported for every dataset.

## Separation and model

Donor locations are the saved training-selected eight-scan fits. Their scan IDs are disjoint from target IDs, and the last donor start plus 300 seconds precedes the first target start. These are chronological windows within the existing sparse 24-scan pools, not full consecutive-acquisition prefixes.

At the fixed donor position, target training observations select a 41-node timing-grid seed per scan and refine eight target timing offsets. Freeze target candidate/background probabilities at that endpoint, then optimize the same expected-component tangent surrogate tested in the previous experiment. Two starts use the ordinary target fit and donor-position endpoint. Selection uses qualified surrogate training score only.

Target training data still determine the target's candidate probabilities: this is earlier-location-assisted association, not independently verified satellite identity. The source/target separation removes the previous N24 donor's reuse of target scans, but does not remove site-conditioned candidate banks or earlier research exposure.

All held comparisons evaluate the unchanged original mixture at the arm's parameters, using its standard training-conditioned within-track predictive likelihood. They are not evaluations on completely excluded target scans or of a new standalone frozen-probability density. Reference distances use the existing spherical convention and an operator coordinate with unknown uncertainty.

## Decision

Do not promote the method yet. The geographic improvement survives disjoint donors, but seven of nine estimates remain outside 1 km and target-only held prediction usually wins. Preserve this as a candidate constraint and retain both geographic and predictive outcomes in further comparisons.

The next useful control is a joint source-plus-target fit at the same total scan budget. That distinguishes an advantage of constraining associations from the benefit of including earlier measurements at all. A convincing method should add value beyond direct donor use and ordinary joint pooling, with failures retained. Avoid selecting donor windows or constraint strength against the known reference.

## Validation and artifacts

All nine timing refinements and all 18 constrained starts qualified. Donor tangency and lower-bound checks passed; scan identity and chronology checks passed for every pair. A synthetic timing test verifies that only timing is optimized even with nonzero geographic gradients. Existing frozen-surrogate tangency and gradient tests remain applicable. Each dataset process completed in 41–47 seconds under its 300-second cap, without retries.

[run.py](run.py), [launch.py](launch.py), [manifest.json](manifest.json), all per-pair outputs and process receipts, and [summarize.py](summarize.py) are retained. The summary verifies the frozen input/code hashes and evaluates reference distance only after selection. Exclusive output creation prevents silent overwrite.

No new RF collection, production changes, golden-fixture edits or remote publication occurred.
