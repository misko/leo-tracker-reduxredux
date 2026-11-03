# Local scan disagreement fails as a subkilometre acceptance rule

The frozen disagreement gate accepts 9 of 18 eight-scan estimates. **Seven of those nine remain at least 1 km from the operator reference**, with a worst accepted distance of 2,212 m. It rejects three of the five estimates below 1 km. Do not promote this gate into accuracy labeling or operational abstention.

| Panel family | Evaluated | Accepted | Accepted below 1 km | Accepted at least 1 km | Rejected below 1 km |
|---|---:|---:|---:|---:|---:|
| Contiguous windows | 9 | 3 | 0 | 3 | 2 |
| Time-balanced sets | 9 | 6 | 2 | 4 | 1 |
| Total | 18 | 9 | 2 | 7 | 3 |

Acceptance is 50%; among accepted estimates only 22.2% are below 1 km reference distance. Without the gate, 5/18 (27.8%) are below 1 km. These descriptive fractions come from overlapping, previously exposed panels; they are not estimates of independent deployment failure rates.

[All 18 panel results](table.md) · [Full-precision summary](summary.json) · [Frozen protocol](PROTOCOL.md)

## Rule and scope

At each saved training-selected eight-scan fit, compute per-scan gradients and observed Hessians, profile each scan's timing nuisance, and form the centered sandwich covariance using eight scan clusters. Repeat with four chronological adjacent-pair clusters. Accept only when both radial scales, `sqrt(trace(covariance))`, are strictly below 1 km. No reference coordinate or target likelihood enters this decision.

The cutoff was frozen before execution and was not changed after viewing results. All nine contiguous and nine time-balanced fits are included. All original fits, 144 scan derivative audits, and 18 summed-curvature checks qualified. Source score and gradient replay gates passed. No refit or additional RF collection occurred.

This is a heuristic disagreement scale, not a calibrated confidence radius. The sandwich approximation relies on local model curvature and cannot establish an absolute bias bound. Four pair clusters are insufficient for asymptotic confidence claims; pairing also cannot capture every long-range dependence. Candidate banks remain site-conditioned and the reference uncertainty remains unquantified.

## What the failure teaches us

The DS8 balanced-2 fit is a concrete counterexample: scan scale 569 m and pair scale 449 m, yet reference distance 2,212 m. Conversely, DS9's early contiguous fit has a 1,281 m scan scale but only 639 m reference distance. Thus low internal disagreement can coexist with a displaced solution, while large disagreement can coexist with a near-reference solution.

This rules out the tested local-disagreement threshold as a sufficient accuracy certificate. It does not establish which physical mechanism caused the displacement: shared model error, association conditioning, timing ambiguity and local-mode behavior remain possible contributors. Nor does the result invalidate using these derivatives to diagnose influential scans.

The next useful distinction is **local uncertainty versus separated solution modes**. Compare fits on disjoint temporal blocks and preserve their location alternatives rather than collapsing all uncertainty to a single local ellipse. Such a comparison must still report failure and coverage; agreement between blocks alone would not prove absence of shared bias. Avoid searching these exposed panels for a cutoff that happens to isolate the five good reference distances.

## Reproduction and checks

[run.py](run.py) reads saved fits and uses the existing audited curvature and covariance implementations. [launch.py](launch.py) freezes input/code hashes and caps each dataset process at 300 seconds. Results and process receipts are retained per dataset. [summarize.py](summarize.py) evaluates reference distance after the gate and verifies the frozen hashes.

Two gate boundary/failure tests passed, along with the two existing covariance tests (mean-variance and within-cluster duplication invariance). Source numerical checks provide the actual-data validation. Exclusive output creation prevents silent overwrite of the completed run; use a separate directory for a new execution.

These artifacts are local. No production contracts, golden fixtures, or remote reports were changed.
