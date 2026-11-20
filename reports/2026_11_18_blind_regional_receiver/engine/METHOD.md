# Blind regional Doppler receiver

Call `receiver.solve(observation, regions, tle_text)` with an observation's
start and cutoff times, the timestamp and contents of the supplied causal
TLE snapshot, and anonymous whole CFO tracks. Each offer gives an opaque ID
and the center of a 25 km WGS84 east–north square at sea level. The search
uses only these offers, the current scan and its supplied orbital elements.
The result is available at scan end.

The receiver sorts each track by sample time, screens malformed tracks,
and collapses exact duplicate records. It keeps up to 64 of the longest
tracks in each group. Whole tracks ending by the acquisition midpoint
nominate one Doppler-shape grid point per tile. Whole tracks starting at
or after the midpoint score those frozen points. A track crossing the
midpoint can enter the pooled coordinate fit. It stays outside both
disjoint groups. The position grid and scoring share the anonymous
satellite shortlist and bounded orbit-time nuisance in `grid.py`.

## Region decision

A region must have at least four supported tracks in each half and a mean
shape score of at least 0.25 in each half. A missing track contributes zero
to the normalized score. The best held score must exceed the next region's
by more than 0.025 when a second region has a positive score.

For each of 19 schedules, add `j/20` of each late track's available start
range to its original start within that range, wrapping modulo the range.
The available range is the second half's duration minus the track's span.
At least four held tracks must have more than one microsecond of available
range. Each shift preserves sample intervals, track values and RF. The
satellite shortlist is recomputed at the changed times. Each schedule
contributes the highest score across all early nominees, at their frozen
coordinates. The observed winner must beat every such set maximum by more
than 0.02. The related schedules provide a specificity check. Their ranks
do not calibrate a false-publication probability.

The four-track minimum and the `1 / (1 + cost / 4)` evidence scale come
from earlier development. A score of 0.25 corresponds to a shape cost of
12 for a single contribution, the inlier cutoff used in an earlier
prototype. The 0.025 inter-region margin is one full-score contribution
on a 40-track scale. The earlier eight-scan time-shift experiment included
an omitted-region false publication at a 0.0113 lead and a correct-region
publication at a 0.0169 lead. The fixed 0.02 lead sacrifices that weaker
development-region acceptance to demand stronger separation. Those scores
came from an earlier implementation on a single roof. Thresholds were fixed
before evaluating the blind inputs.

## Coordinate decision and diagnostics

A region pass is recorded in `diagnostics.region_result`. To publish the
coordinate, fit the late tracks independently and check that their optimum
is within 5 km of the early optimum. Fit all selected whole tracks in the
winning tile and require the pooled optimum to be within 4 km of both
disjoint optima and more than 1 km inside every tile edge. The pooled and
late fits also need at least four supporting tracks and a mean evidence
score of at least 0.25. The 5 km compatibility threshold follows the
prior study's descriptive position tolerance. The 4 km pooled radius and
1 km edge margin are fixed engineering choices at the scale of one coarse
grid spacing and several fine steps, respectively. Fit compatibility
measures stability on the available tracks. Geographic accuracy requires
external scoring.

The public coordinate and region ID are null when the fix is withheld.
The best diagnostic coordinate comes from the winning region's pooled fit
or its early fit if pooling fails. With insufficient disjoint evidence,
the receiver retains the strongest pooled solution across the supplied
regions when available. This forced diagnostic never grants acceptance.
Exact ties within `1e-12` use numeric center order for forced diagnostics.
If the same tied center has multiple IDs, the coordinate is retained and
the ID stays null. Candidate order and opaque labels cannot grant a
publication on a tie. The stage times and total wall time are host compute
measurements from arguments already in memory. Work counters record tile
construction, grid fits, fixed-point scores, and completed null schedules.
SGP4 state-evaluation counts are available for the shared sky and each tile.

## RF coefficient control

With one fixed RF value per track, `c × (RF_GHz − 11.5)` is constant over
the track. Subtracting the track level removes this term from nomination and
shape scoring, including the position fits and every changed-time control.
The model identifies shape and has no data column for `c`. The synthetic
component test compares the same Ku-band CFO-shape observations with
the RF-dependent level present and after correcting it with the coefficient
fitted from the known synthetic level differences. Track times, candidate arcs,
thresholds and work are matched. The test checks score and shape-RMS agreement
separately from the identical published position, and checks the position
against the planted coordinates.

Run the component checks from the repository root.

```sh
OPENBLAS_NUM_THREADS=1 .venv/bin/python -m pytest -q \
  reports/2026_11_18_blind_regional_receiver/engine/test_receiver.py
```
