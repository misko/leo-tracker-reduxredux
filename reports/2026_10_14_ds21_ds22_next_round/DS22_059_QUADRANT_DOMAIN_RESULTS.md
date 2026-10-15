# DS22-059: nine-start quadrant expansion still excludes the configured station

The expanded B experiment's nine 25 km search disks all exclude the configured
station. The nearest disk misses it by **45.177806 km in the optimization
coordinates**. Therefore that experiment could not have achieved sub-kilometre
localization against this reference, despite all 27 fits converging.

This is a post-seal geometric audit, with zero objective evaluations and zero
fits. DS22's reference remains configured and unconfirmed. It is inside the
original 250 km prior, at local coordinates (-87.035796, -80.990860) km.

| Start | Disk center east, north (km) | Distance to configured point (km) | Miss beyond 25 km radius (km) |
| --- | --- | ---: | ---: |
| 0 | 106.25, 156.25 | 306.010824 | 281.010824 |
| 1 | 131.25, 156.25 | 322.384731 | 297.384731 |
| 2 | 50, 150 | 268.580690 | 243.580690 |
| 3 | 202.094104, 147.166481 | 368.309478 | 343.309478 |
| 4 | 79.300496, 49.710646 | 211.543484 | 186.543484 |
| 5 | 12.353311, 13.708321 | 137.281206 | 112.281206 |
| 6 | -50, 50 | 136.125882 | 111.125882 |
| 7 | 150, -150 | 246.876953 | 221.876953 |
| 8 | -150, -50 | 70.177806 | 45.177806 |

All three channel views use these same disks. The original six-disk coverage
audit was correct; adding three quadrant-selected centers reduced the coverage
gap but did not eliminate it. The prior finding that selected endpoints were
interior to their disks also remains correct. Interior endpoints do not prove
that the union of search domains covers the declared prior region.

This changes the interpretation of the earlier negative quadrant result:
it demonstrates a band-score tradeoff among the searched basins, but cannot
rule out a localization repair through complete coverage of the original prior.
The next coverage intervention should use a deterministic tiling of that prior,
with candidates and starts retained independently of reference coordinates.
The configured location must not select a cell, radius, or winning endpoint.

Source `f767689e1`; two component tests and the actual sealed-data audit passed.
The first implementation, `9dd99e7f1`, failed while unpacking the existing guard's
tuple return, before writing an output or evaluating any objective. The corrected
run uses the separate `ds22-059-quadrant-domain-v2` namespace; neither the original
27 fits nor their receipts were modified.

Receipt:
`/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-059-quadrant-domain-v2/report.json`.
It binds the complete quadrant terminal, original protocol, post-seal comparison,
reference authority and diagnostic sources. No model or cohort metric is promoted.
