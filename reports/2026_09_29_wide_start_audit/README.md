# Distant starts return nearby, but do not recover the best known N24 optimum

All twelve corner-start runs satisfy the existing local optimizer gates, yet
none recovers or improves the existing N24 training score. Final geographic
positions lie 31–973 metres from the best known solution. Keep the existing
N24 fits; the additional starts do not justify replacing them or claiming
global optimization.

| Dataset | Qualified distant starts | Training-score deficit range | Distance from existing N24 position |
|---|---:|---:|---:|
| DS7 | 4/4 | 67.658–167.652 | 136–401 m |
| DS8 | 4/4 | 199.363–325.980 | 31–271 m |
| DS9 | 4/4 | 96.815–568.789 | 214–973 m |

Deficits are original q020 training log-score units, not accuracy losses.
Distances are differences in the model's east/north coordinates, not errors
against ground truth. All four starts per dataset are at east/north ±8 km,
about 11.3 km from the configured center. No reference error chooses a start
or endpoint in this audit.

## What this tests

The [protocol](PROTOCOL.md) freezes the four starts, bounds and optimization
before execution. At each corner, initialize each scan's timing using its
training-only 41-node likelihood grid. Fit the unchanged q020 mixture with
shared geographic coordinates and 24 independent recording timing parameters,
retaining the original ±12-km geographic and ±5-second timing bounds.

The source observations and candidate banks remain identical to those used
by N24. Bank states support evaluating new observer coordinates, but candidate
selection was geographically conditioned. Accordingly this is an initialization
audit inside the existing model domain, not a removal of geographic-prior
information or evidence of global search coverage. The configured center and
search bounds also remain unchanged.

Convergence from distant corners to positions near the known fit supports
some geographic constraint within these banks. It does not prove that a new
site with different candidate support would behave similarly. In particular,
the preceding full-catalogue domain probe already found omitted leading
candidates at much larger offsets.

## Local qualification is not recovery of the best likelihood

All runs report optimizer success, interior endpoints and passing gradient
checks. Maximum gradient-audit discrepancy is 1.60e−5, below the existing 0.02
gate. Training-grid scores replay the scalar likelihood within 1e−7. There
are no exceptions, unqualified cases, timeouts or retries. Each corner result
is saved separately; all dataset processes exit zero within their 300-second
caps. Frozen source hashes and Ruff checks pass.

DS8 illustrates why geographic proximity alone is insufficient: one endpoint
is only 31 metres from the existing location but has a 325.98-unit lower
training score. Its complete nuisance-parameter state must also be assessed.
This report does not attribute the score deficit to timing, associations or
any other individual mechanism; it records different locally stationary
endpoints under the same objective.

## Next bounded optimization test

The initial timing grid was evaluated at the distant corner, before geography
moved. A useful next test is one fixed round of training-only timing re-selection
at the converged geographic point, followed by the same joint optimizer. Include
each current continuous timing value alongside the grid so initialization cannot
lower that scan's score. Compare both the best wide-start endpoint and the
existing N24 endpoint, retain failures and select only by training likelihood.

That test could distinguish recoverable initialization problems from model
mismatch. It would still require excluded-scan evaluation before claiming an
accuracy improvement, and would retain the same site-conditioned bank limitations.

See [summary](summary.json), per-corner checkpoints, per-dataset outputs and
process receipts. No target evaluation, new location-reference comparison,
RF collection, production edit or publication occurred. Artifacts are local.
Reproduce with `batch.py prepare`, `batch.py run` and `summarize.py` under
NumPy/SciPy in a fresh output context.
