# C053 stalled feasible state has smooth, feasible descent

The bounded audit found no local visibility event or free-coordinate active-bound obstruction at the training-selected best feasible fixed-profile state. All18 signed perturbations were feasible without projection, and all19 native visibility masks were identical. Analytic directional gradients agree with finite differences; small feasible downhill steps lower the objective. The failed restart therefore cannot be explained by a bad local gradient, a visibility discontinuity at these sampled scales, or an active free-coordinate bound.

| Direction | Analytic derivative | Central FD at1e-5 | Gradient-derived curvature at1e-5 | J change at positive1e-3 |
|---|---:|---:|---:|---:|
| All free parameters | −1391.678715 | −1391.678710 | 287736.566 | −1.247774 |
| Satellite timing only | −1172.999577 | −1172.999568 | 133705.127 | −1.106101 |
| Receiver/RF/group only | −326.491560 | −326.491562 | 262727.097 | −0.195125 |

Curvatures were also positive at1e-3 and1e-4; the latter values were287737.417,133706.246 and262726.978. These are directional curvatures for maximum-component-normalized directions, not full-Hessian eigenvalues. They support checking numerical scaling/line-search conditioning, but neither prove an ill-conditioned full Hessian nor certify positive definiteness, a local optimum, uncertainty, or global behavior.

The baseline exactly replays J50360.032179 and original physical KKT747.683484. Maximum free-chart gradient is268.202453 in timing and179.637970 in calibration. There are no active normals in the free chart: geography is fixed, so its disk-boundary normal has zero free-coordinate derivative. Original physical domain checks still apply to every probe. The active-rank result must not be mistaken for interior geographic feasibility.

Coordinate units are the original solver chart: receiver offsets200 Hz, slopes2 Hz/s, RF coefficient200 Hz/GHz, direct satellite shifts1 second, and the original group nuisance scales saved in the result. Directions were constructed by active-cone projection, but perturbed states were never projected or repaired. Each signed probe and feasibility result is saved; none was omitted. There were no references, held observations or optimizer calls.

Actual cost:19 native objectives plus19 explicit native orbit predictions,45.660 seconds including genuine preparation/authority, with a120 second internal and135/140 second independent external bound. Three component tests and Ruff passed. Frozen source/protocole12435791; namespace `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-c053-directional-audit-v1`; result SHA256 `7e4876918f36f577281056921351a2e4bb0ae1949a9a93eb68eeaaf47a9f5ac9`.

Before another restart, a bounded full free-coordinate Hessian/conditioning audit or a separately qualified conservative preconditioned descent policy would be more informative than repeating identical SLSQP. No such new experiment is included here, and the existing strict selector remains unchanged.
