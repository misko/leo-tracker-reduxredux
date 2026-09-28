# Read-only receiver-pose provenance audit

## Finding

There is no hard coordinate-sign mismatch between the frozen T-arm feature and the pose authority
used for these recordings. The code assigns receiver signs `(-1,+1)` and computes
`sign * sin(10 deg) * east`: receiver 0 is the nominal west-facing side and receiver 1 the
nominal east-facing side. That agrees with the stored authority's RX0/physical-RX1 azimuth 270
degrees and RX1/physical-RX2 azimuth 90 degrees.

This agreement is only with a **nominal, provisional pose model**. The repository does not contain
a surveyed world-frame antenna pose, a verified cable trace from physical connectors to software
receiver indices, measured receiver elevation angles, gain patterns, or RF phase centers. The
T arm therefore tests whether data follow this recorded nominal east/west coding. It does not test
a verified physical 20-degree separation between antenna axes.

## Evidence chain

The original ten-record cohort is listed with its six calibration and four evaluation sessions in
[the direction-subset report](../2026_09_27_roof_direction_subset/REPORT.md#corpus-and-selection).
That report already describes the pose as operator-supplied coordinates, nominal opposite
east/west tilts and provisional receiver mapping, with altitude, world tilt, RF phase centers and
gain patterns unmeasured. It also states that the earlier coefficient sign was conditional on the
provisional mapping and did not independently survey the axes.

The four later confirmation records are listed in
[the receiver-geometry inventory](../2026_09_28_rx_geometry_confirmation/INVENTORY.md#decision).
The inventory says all four use the same pose authority and are disjoint from the ten pilot
sessions. Inspection of the pose-bearing manifests for all 14 session IDs found the same authority
revision, `gauss-r20-roof-20260926-v1`, fixture digest
`sha256:6e6f8798e1465691fdb6ad973bc37443651408c4060f091144b1a470fb0817a4`, and station
coordinates 37.849056280893684 N, -122.48575489722863 E.

For every one of the 14 records, the manifest's earliest capture start is later than the
authority's `valid_from_utc_ns = 1790465417000000000`; none straddles the conservative pose-change
boundary. The authority's time evidence says the move was approximately 23:30 UTC and that this
boundary is the first inspection after the completion report, not an exact movement timestamp.
The selected captures are therefore applicable under the repository's conservative validity
rule, while the move time itself remains approximate.

The authority records these fields consistently:

| Field | Recorded value | Evidential status |
|---|---|---|
| fixture | LT3D-001A | Operator says the `.20` fixture is identical to the prior `.21` fixture |
| mount separation | 0.08 m | Nominal |
| outward tilt | 10 degrees per side | Nominal; symmetric 20-degree included angle is inferred |
| receiver 0 | connector `RX1`, azimuth 270 degrees | Mapping status `provisional` |
| receiver 1 | connector `RX2`, azimuth 90 degrees | Mapping status `provisional` |
| azimuth frame | geographic north | Marked `geographic-north-assumed` |
| receiver elevation | null | Unmeasured |
| phase-center baseline ENU | null | Unmeasured |
| altitude/datum | null | Propagation used zero altitude approximation elsewhere |

The orientation evidence is unusually explicit: “RX2 points east, RX1 points west,” followed by
“provisional physical RX1/RX2 to zero-based software RX0/RX1 mapping; not a cable trace.” It also
says antenna pointing does not establish a directed phase-center baseline. These statements are
present in the pose objects embedded in
[the original cohort manifest](../2026_09_27_roof_direction_subset/evaluation_manifest.json)
and [the four-record manifest](../2026_09_28_rx_geometry_confirmation/manifest.json).

## Model correspondence

The implemented feature definition is visible in
[rx_geometry_fit.py](/home/mouse9911/gits/leo-tracker-reduxredux/tools/rx_geometry_fit.py:26).
It takes line-of-sight coordinates ordered east, north, up, then uses receiver 0 sign `-1` and
receiver 1 sign `+1`. Consequently:

- receiver 0 tilt feature is `-sin(10 deg) * LOS_east`, consistent with a nominal westward tilt;
- receiver 1 tilt feature is `+sin(10 deg) * LOS_east`, consistent with a nominal eastward tilt;
- their modeled boresight axes are separated by 20 degrees only under the assumed symmetric
  ten-degree outward tilts from the common up axis;
- the interaction term multiplies that nominal signed-east feature by LOS up.

The model does not read pose azimuth, tilt, receiver mapping, or capture-time pose fields when it
builds these features. It hard-codes the nominal signs and ten-degree angle. Pose applicability was
established upstream through bound manifests; it is not revalidated in the geometry dataset or
fit. This is internally consistent for the frozen cohort, but a future cohort with another pose
revision could be silently mis-modeled unless the feature builder binds and validates the pose
revision explicitly.

## Known and unknown

Known within the repository:

- all 14 sessions have hash-bound pose companions using one revision and fixture digest;
- all captures begin after the conservative validity boundary;
- the operator-reported physical pointing is RX1 west and RX2 east;
- the recorded provisional software mapping assigns receiver 0 to RX1 and receiver 1 to RX2;
- the feature sign convention matches that recorded provisional assignment.

Unknown from the retained evidence:

- whether the physical-to-software mapping was verified by cable trace at capture time;
- the actual world-frame tilt magnitude, receiver elevation, roll, yaw error or mount asymmetry;
- the RF phase-center positions or a directed baseline vector;
- whether antenna patterns are symmetric, stable, or well represented by a linear signed-east
  reception term;
- whether the approximate move-completion time hides motion before the conservative boundary.
  The selected captures are after that boundary, so this last uncertainty does not create a known
  cohort violation.

## Scientific implication

The failed T controls do not reveal a known receiver swap or coordinate error. They show that the
nominal signed east/west response did not generalize under the frozen model. Because the receiver
mapping and world tilt are provisional, the swap control is best interpreted as sensitivity to
the assumed sign assignment, not as a test against a surveyed physical alternative. Reversal
likewise tests trajectory specificity under the nominal feature rather than fixture correctness.

Do not claim that cables were reversed or that the fixture was physically misaligned from these
results. The supported conclusion is narrower: physical pose uncertainty is sufficient to block
a calibrated 20-degree receiver-geometry interpretation. A future directional experiment should
bind each capture to a measured antenna-axis vector and verified connector-to-software mapping,
or treat orientation/sign as a predeclared nuisance and confirm the selected convention on unused
records.
