# DS6 local uncertainty audit

The corrected single-scan estimator's local likelihood curvature is severely
overconfident on DS6. Its nominal 95% horizontal ellipses contain the operator
reference in only 2/43 scans. Grouping scores by track or inferred satellite
widens the regions substantially, but neither grouping produces nominal
coverage. This does not alter a location estimate or establish an irreducible
accuracy floor.

| Covariance approximation | Reference inside nominal 95% ellipse | Median major-axis radius | Major-axis radius below 1 km |
|---|---:|---:|---:|
| Inverse observed information | 2/43 | 578 m | 33/43 |
| Track-cluster score sandwich | 19/43 | 3,529 m | 0/43 |
| Training-MAP satellite-cluster score sandwich | 26/43 | 5,077 m | 0/43 |

All 43 corrected baseline winners and 2,526 included tracks are retained. No
scan, track, parameter or cluster is selected by the reference coordinate.
Per-track training mixture scores supply central derivatives in east, north
and scan timing. Inverse information includes the timing nuisance before
taking the horizontal covariance block. Cluster score sums use a finite-group
correction and centering to remove the small nonzero numerical total score.
No per-scan uncertainty multiplier is fitted to geographic error.

The second grouping uses the training-MAP catalogue row shared across receivers
and channels within a scan; these are inferred identities. Median group count
is 27. Of the included tracks, 129 have MAP mass below 0.9 and 220 below 0.99;
the lowest mass is 0.183. The grouping does not integrate identity uncertainty,
and neither sandwich is a validated confidence distribution. Scans also share
one location, orbit sources and development history, so the descriptive
coverage counts are not independent Bernoulli trials.

Halving all finite-difference steps leaves coverage counts unchanged at
2/43, 19/43 and 26/43. Median radii change by less than 1 m. Three scans have
more than 5% change in at least one cluster radius: `cd6a029d633dcc0e` (8%),
`e84e2f55976c0a8c` (9%) and `a077447f07d9f81f` (74%). The last scan's individual
ellipse is particularly sensitive to local numerical/nonquadratic behavior;
it must not be presented as a stable confidence region. Primary and half-step
results are both retained unchanged.

The audit supports accounting for dependence and model misspecification before
making precision claims. It does not show that changing covariance alone will
improve position. Remaining undercoverage can reflect bias, local curvature
failure, uncertain grouping and finite-sample effects; this experiment does
not identify a unique physical cause.

Four tests passed: duplication invariance of cluster covariance, direct
cluster-sum agreement and explicit invalid-information handling, horizontal
ellipse construction with timing nuisance, and complete all-43 provenance and
covariance reproduction. A test initially resolved another report's generic
`summarize` module; its import now binds this report's exact file. The original
baseline summary was checked against its existing seal and remained identical.

The accepted location results remain 761.85 m for the all-scan joint estimate
and 6/43 sub-kilometre individual scans. The broader goal remains active.
The pose authority supplies no altitude, while the current geometry assumes
zero ellipsoidal altitude. Altitude sensitivity and the numerically sensitive
local likelihoods are concrete next checks; ground truth must remain outside
fitting. An optional request for independently known antenna altitude is
pending, and no new RF collection or production change has occurred.
