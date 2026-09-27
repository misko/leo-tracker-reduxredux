# DS6 receiver curvature: converged conditional audit

All 43 sealed DS6 scans are included. At each frozen independent-scan baseline
location and timing, candidate identity is chosen using training observations
only and fixed across all three arms. Correlated observations remain in their
original random whole-visit groups (seed 2026092711). Ground truth is not read.

| Held-out log-score comparison | Scans improved | Total gain | Median gain |
|---|---:|---:|---:|
| Linear receiver drift versus track offsets only | 33/43 | 835.21 | 10.56 |
| Quadratic versus linear receiver drift | 40/43 | 725.25 | 13.05 |

Positive scores indicate improved predictive density, not metres of accuracy.
All fits converged with a 2000-iteration limit. Repeating the quadratic fit with
a 4000-iteration limit changed neither training nor held score on any scan.
The initial 80/160-iteration audit remains in the sibling directory for audit;
only the numerical iteration limits changed in this follow-up.

The model is Student-t4 with fixed 100 Hz scale, independent track offsets and
receiver-shared polynomials in `(time-150)/150`, with coefficient prior standard
deviation 750 Hz. Basis columns are centered using training observations only
and scaled by 11.2 GHz / actual RF. This models effective frequency drift before
normalization; it does not establish a hardware clock calibration.

The held-out improvement warrants a matched location refit with linear and
quadratic arms. It does not establish a new position result: the residual trend
can also absorb location, propagation or assignment error. Prior free-drift
experiments improved prediction while worsening location, so a geographic
comparison remains essential. Retain the inherited catalogue mixtures in that
refit rather than treating the diagnostic's MAP labels as certain identities.
Select all fitted parameters and optimizer starts by training score; evaluate
the roof-coordinate error only after outputs are frozen.

The currently verified joint 43-scan estimate remains 772 m from the operator
reference. Independent-scan baseline results remain 6/43 below 1 km, median
2.425 km. This diagnostic does not change either figure or complete the broader
sub-kilometre objective.

`scores.csv` contains every scan's comparison. `protocol.json` binds the source,
baseline outputs, inputs and transitive numerical dependencies. Tests cover
synthetic recovery, objective stationarity, held-data isolation, all-43
membership, unchanged assignments, convergence and inherited visit grouping.
