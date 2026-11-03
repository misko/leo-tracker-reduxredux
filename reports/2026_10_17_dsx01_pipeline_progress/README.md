# DSX01 progress versus frozen standard analysis

The track builder covers91.3% of all20,084 GLRT winners; satellite association and
position accuracy remain unresolved. Standard results below are the recorded
shared-scan-q-v2 outputs frozen with DSX01, not a rerun of today's production code.
Every percentage uses the full original winning-GLRT population for that scan.
Standard terminal positions/hashes and original association flags were checked.
Every Graph observation ID, time, receiver/channel and native alias was checked
against that same frozen population. Ground truth is (37.849061591561885, -122.48574968092912), assumed0m height.
Errors are horizontal great-circle distances, Earth radius6371.0088km.

| Scan | GLRT points | Graph tracked | Standard satellite assoc. | New fixed-GPS satellite compat. (fitted c) | Standard position error km |
| --- | --- | --- | --- | --- | --- |
| S01 | 4797 | 4487 (93.5%) | 1643 (34.3%) | 393 (8.2%) | 132.176 |
| S02 | 3524 | 3185 (90.4%) | 1657 (47.0%) | 793 (22.5%) | 133.790 |
| S03 | 3988 | 3609 (90.5%) | 3091 (77.5%) | 913 (22.9%) | 5.239 |
| S04 | 3719 | 3348 (90.0%) | 2381 (64.0%) | 402 (10.8%) | 258.655 |
| S05 | 4056 | 3709 (91.4%) | 2450 (60.4%) | 1120 (27.6%) | 7.443 |

Graph tracked means assigned to a polynomial, not to an identified satellite.
The new all-five satellite column is the completed fragment-matching plus
lossless consolidation arm, with1000Hz Gaussian component constants and a
separate offset/drift for each scan/RX/band, using latest causal Space-Track TLEs.
Its position is FIXED at ground truth, with residual-structure gates. Standard
associations are posterior classifications at each standard estimated position.
The criteria, candidate ephemerides and fixed/blind conditions differ: this is
a progress inventory, not a controlled identity-accuracy or algorithm ranking.
Independent true satellite labels are unavailable.

The paired c0 arm admits3610 points versus3621 for fitted c:393/793/902/402/1120
versus393/793/913/402/1120 on S01–S05. Lossless candidate consolidation gives
21/36/41/19/49 fitted-c groups, averaging18.7/22.0/22.3/21.2/22.9points/group.
Polynomial pre-merging reduces676Graph fragments to456components and retains
their18338points, but hard pre-merging before satellite selection loses coverage.
The safer current path matches fragments, then joins compatible same-ID results.

## Newer S01 orbital-phase pilots

| S01 model | Points / all GLRT (%) | Blind position error km |
| --- | --- | --- |
| zero_c0 | 190 (4.0%) | 5.734 |
| zero_fitted_c | 207 (4.3%) | 5.616 |
| shared_c0 | 2237 (46.6%) | 13.434 |
| shared_fitted_c | 2186 (45.6%) | 13.434 |

These are independent geographic searches with matched c arms. S02–S05 have
not yet received the newer phase model's blind searches; no missing error is zero.
The zero-phase control gives5.734/5.616km versus shared phase13.434/13.434km.
At the FIXED ground-truth location shared phase gives2181points(45.5% of4797),
or1975points(41.2%) with the tighter ±1Hz/s drift model. Fixed-site fit is not a
position estimate. Several drift limits remain active, flagging weak calibration.
No DSX01 scan has demonstrated the0.5km target in these new blind results.

## Active measurement investigation

Continuous known-pilot CFO was qualified on14/16DS22 and15/16DSX response-selected
points. Complete-track DS22 now evaluates602points, with515passing unchanged
estimator controls. These measurements have not entered the position results.
The complete-track DSX extension exposed11source-time joins outside the small
panel's0.51ms tolerance (rangeup to0.5205ms); it stopped before producing fits.
That provenance issue is being resolved rather than silently discarding points.
No source recording, production product, detection or original population changed.

![Stage coverage and standard position error](comparison.png)

The figure separates track coverage from satellite classification. CSV andJSON
provide all counts, consolidated-track statistics, source bindings and errors.
Full137-member DS22 fixed-site coverage is complete in the physical-model report;
blind accuracy remains evaluated on pilots, not the whole DS22 population.
