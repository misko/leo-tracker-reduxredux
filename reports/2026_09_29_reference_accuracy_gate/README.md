# Reference provenance and a conditional sub-km validation gate

The roof reference is **operator-supplied position evidence**, not a radio-fit
output. The station authority explicitly says its altitude and survey uncertainty
were not supplied and interprets its coordinates as WGS84. Thus the missing
evidence is the coordinate's measurement source, datum confirmation and bounded
horizontal error; it is not necessarily a centimetre survey.

For a fixed estimate and an independently supported horizontal reference bound R,
the geodesic triangle inequality gives:

```
true horizontal error ≤ distance(estimate, reference) + R.
```

Consequently, a point can be certified below 1,000 m only when that sum is
strictly below 1,000 m. No bound is assumed here. All current gates remain
`unverified_reference_bound`; the conditional thresholds below are requirements,
not newly established accuracy results.

| Estimate | DS7 distance / required R | DS8 distance / required R | DS9 distance / required R |
|---|---:|---:|---:|
| Configured center, no measurement fit | 807.64 m / R < 192.36 m | same | same |
| N24 fit | 386.88 m / R < 613.12 m | 389.79 m / R < 610.21 m | 107.43 m / R < 892.57 m |
| Geometry-selected eight | 1,830.17 m / cannot certify | 986.30 m / R < 13.70 m | 396.31 m / R < 603.69 m |
| Score-balanced eight from N24 | 390.15 m / R < 609.85 m | 403.30 m / R < 596.70 m | 97.80 m / R < 902.20 m |

Numbers use WGS84 ellipsoidal horizontal distance. Earlier report tables used
the repository's spherical haversine convention; the configured-center value
there is 809.03 m, versus 807.64 m here. Both computations are preserved, and
the small metric difference is not a model improvement. Exact machine-readable
limits, rather than rounded table boundaries, determine the strict gate.

For example, an independently justified 100-m bound would suffice for all
three N24 and score-balanced estimates on these fixed recordings. It would
also suffice for the configured center without any radio inference. Conversely,
the marginal DS8 geometry-selected result needs a much tighter bound. These
examples assume the reference applies to the antenna location and period and
that datum and coordinate errors are included in the supplied bound.

## What the repository establishes

The inspected [station authority](../../deploy/station/gauss-r20-roof-20260926-v1.json)
records the operator-supplied roof coordinates and approximate movement time.
The [operations record](../../docs/operations/radio20-roof-pose-20260926.md)
explains pose binding, provisional connector mapping, unknown phase-center
baseline and unknown altitude/elevation. All 72 N24 source scan intervals fall
within the authority's timestamp validity range. This timestamp check is not
a complete radio-serial or per-capture companion-binding audit.

The three checked deployment station JSONs and two station-topology qualification
JSONs supplied no additional surveyed location uncertainty. The previously
exported capture timing authority contains host realtime/monotonic brackets
and device counters, but no independent historical UTC accuracy or discipline
reference. This is a scoped repository audit, not an exhaustive search of
external survey records, receiver logs or system journals.

Location and timing evidence serve different purposes. Historical GNSS/PPS or
equivalent clock evidence would help distinguish physical timing errors from
model nuisance offsets. It is not logically required to measure a fixed
estimate's horizontal error if the receiver's true location is independently
bounded. Neither a position bound nor clock calibration by itself establishes
generalization to new sites or unseen recordings.

## Consequence for the goal

The configured-center baseline already lies within 1 km of the supplied roof
point. Therefore, crossing the 1-km threshold alone is not sufficient evidence
of radio-derived localization skill on this site-conditioned benchmark. Report
improvement over the no-measurement center, predictive transfer and geographic
prior/candidate-bank conditioning alongside the absolute error.

The immediate evidence needed is a provenance record for the roof coordinate:
how it was obtained, when/where it applies, its datum, and a defensible horizontal
error bound that includes displacement to the antenna. If the bound is
probabilistic, preserve its stated coverage; do not turn a one-sigma or 95%
radius into a deterministic guarantee. Do not infer uncertainty from the many
decimal places in the coordinate.

## Verification and reproducibility

The [gate implementation](study.py) explicitly refuses to certify a missing
bound. Tests cover missing bounds, the strict 1,000-m boundary and invalid bounds.
[Ellipsoidal results](wgs84-results.json) record the GeographicLib version and
source hashes; [spherical results](results.json) preserve parity with earlier
reports. Source fits must be qualified before inclusion. Hashes and Ruff pass.
No coordinate, model fit, production contract or historical report was changed.

No RF was collected and nothing was published. Artifacts are local. Run
`study.py` with Python, then `wgs84.py` under GeographicLib in a fresh output
context to reproduce both metrics. This audit sharpens the validation requirement;
it does not claim the missing reference bound has been supplied.
