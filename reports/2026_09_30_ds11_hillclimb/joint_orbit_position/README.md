# Causal orbit uncertainty: geographic pilot fails

The frozen orbit arm worsens position error on both scans despite improving
held Doppler prediction at the baseline positions. It does not advance.

| Scan | Original IID (m) | Joint zero (m) | Orbit uncertainty (m) | Linear uncertainty (m) |
|---|---:|---:|---:|---:|
| 0 | 765.072 | 765.072 | 1512.799 | 3204.420 |
| 16 | 2153.140 | 2153.140 | 2337.572 | 4466.518 |

All twelve starts exit successfully and pass endpoint qualification. All six
arm/scan selections were sealed by highest qualified training score before
geographic scoring. No timeout, retry, candidate pruning or prior tuning.
The selected zero-revision endpoints reproduce original accuracy within 0.1mm.
Some starts find different qualified basins; two starts do not establish global
optimality. No alternative endpoint is selected using reference error.

Two selection/gate tests pass. Independent verification checks all source
hashes, twelve terminal receipts, endpoint qualification, training selection,
the sealed outcome and distance/gate calculations. Distance replay agrees
within 4.55e-13m; optimization itself is not independently replayed.

All original and older orbit records are causal. This model shares satellite
identity and revision coefficient across conditionally associated tracks, uses
frozen DS7/DS8 priors, and profiles separate track CFOs. The matched linear arm
performs worse still, but that does not justify promotion of the orbit arm.

The evidence separates predictive flexibility from location accuracy: a
historically useful residual direction can move the geographic optimum away
from the reference. Possible explanations include confounding with geometry,
conditional source grouping, prior transfer and local optima; this pilot does
not distinguish them. Learning a tighter prior from these two position errors
would be benchmark tuning. A future prior needs independent geometric or orbit
calibration evidence before another geographic expansion.

See [frozen protocol](PROTOCOL.md), [plan](plan.json), [all attempts and training
selections](selections.json), [outcome](outcome.json), and [verification](verification.json).
