# DS21-009 fixed discovery-coverage policy transfer

The unchanged dense-grid control completed on DS21-009 with **100 visited points, 300 stored fits and 299 stationary fits**, compared with 298 stationary fits in the original discovery. Its first two selected points are unchanged. The third training-selected fallback changes from the distant `[62.5, 212.5]` to `[-75, -75]`, placing all three control proposal centers within 25 km of the configured reference in optimizer coordinates. This is discovery-only evidence; it does not establish final A/B/C accuracy or a 0.5 km result.

The [fixed protocol](DISCOVERY_COVERAGE_CONTROL_PROTOCOL.md) transfers the DS21-013 control without tuning: levels 50/25/12.5 km replace 100/50/25/12.5 km; the 100-point budget, all-view priority, original observations, priors, fit options and full regional bank remain matched within this case. The 50 km initial grid consumes 80 points, leaving 20 for refinement. The original and control each use DS21-009's 983-candidate full bank. Their point-local bootstrap unions can vary with geography; full-bank equality does not imply identical candidate support at different points.

## Receipt and search checks

The [independent receipt audit](DISCOVERY_COVERAGE_009_AUDIT.json) verifies 404 live/archive control source bindings, the unchanged 402-source base, exact case/census/membership/partition bindings, 200 point receipts and their launch/termination triplets, both complete slice inventories, and exact hierarchy and training-selector replays. It performs standard-library metadata/hash/scalar arithmetic only, with no optimizer, likelihood, orbit or reference-function calls. Stored stationarity certificates are checked without recomputing KKT. The full control terminal was sealed before evaluation was permitted.

| Discovery | Visited points by spacing, km | Deferred cells | Stationary all / low / high | Total stationary | Terminal elapsed, s |
| --- | --- | ---: | --- | ---: | ---: |
| Original | 100: 16; 50: 30; 25: 27; 12.5: 27 | 83 | 99 / 100 / 99 | 298 / 300 | 333.150031 |
| Fixed control | 50: 80; 25: 13; 12.5: 7 | 117 | 99 / 100 / 100 | 299 / 300 | 329.850037 |

Both stop at the 100-point budget. The configured discovery slice remains bounded by 480/495/500-second internal/TERM/KILL limits. There are no missing point-view fit results, recorded exception entries, orphan launches or failed slices. The root process elapsed receipt is 329.851145 seconds; the table uses the saved terminal elapsed field.

The sole control nonstationary fit is all-view `[-62.5, -62.5]`, KKT 0.014326643, solver success true, boundary true. The original run has the identical numerical failure at that point, plus high-view `[-150, 150]`, KKT 0.003600135, solver success true and boundary true. The second point is absent from the control visit set, so it was not repaired. The fixed threshold remains 0.001; failures remain saved and excluded from selection.

## Selected centers and visited support

| Order | Selector provenance | Control center, km | Local candidate count | Saved geodesic error, km | Optimizer distance, km | Signed 25 km disk slack, km |
| ---: | --- | --- | ---: | ---: | ---: | ---: |
| 0 | Low-view minimum | [-87.5, -62.5] | 23 | 18.496084 | 18.496686 | 6.503314 |
| 1 | High-view minimum | [-87.5, -87.5] | 20 | 6.525495 | 6.525671 | 18.474329 |
| 2 | All-score fallback | [-75, -75] | 22 | 13.444296 | 13.444359 | 11.555641 |

The original first two centers and their local unions are identical. Its third fallback `[62.5, 212.5]` has optimizer distance 329.390102 km and disk slack −304.390102 km. The all-view minimum in both runs is `[-81.25, -68.75]`, objective 35165.412083, but it is only 8.838835 km from the first selected point and fails the unchanged 12.5 km separation rule. Thus the third row is an all-score fallback, not the all-view minimum. Its selection score is 35797.019036, versus 35503.515224 for the original distant fallback; geography improves for that selected row despite its higher training score.

Both runs' nearest **visited** point is `[-87.5, -87.5]`, at 25 km spacing and optimizer distance 6.525671 km. Original discovery already visited nearby support: seven visited points lie within 25 km of the configured reference, compared with five in the control. This transfer therefore does not demonstrate an absence-of-visits recovery like the original DS21-013 case. It preserves the two nearby selected centers and changes the third one; it does not uniformly increase local visit density or guarantee 25 km coverage across the prior.

Plane distances and signed slacks use the already audited post-seal reference optimizer point from DS21-013, after checking exact equality of the two cases' original prior and binding the reference/coordinate sources. They are Euclidean optimizer-coordinate arithmetic, not recomputed geodesic errors. The geodesic column copies the control's saved post-seal evaluation rows. A nearby visit alone does not establish a favorable score or selection; selected discovery centers are not final model estimates.

## Training-score comparison

| View | Original minimum | Control minimum | Original median | Control median |
| --- | ---: | ---: | ---: | ---: |
| All | 35165.412083 | 35165.412083 | 40071.083281 | 39982.745337 |
| Low | 18168.202401 | 18168.202401 | 20474.529933 | 20837.558693 |
| High | 15343.908277 | 15343.908277 | 17568.010241 | 17589.641067 |

All three stationary view minima are unchanged. The all-view median decreases slightly, while low/high medians increase. These distributions cover different visited point sets and local candidate unions, so they are descriptive training-fit effects rather than a global common-support objective comparison or position-accuracy proof.

There are **43 common visited points**, all with identical candidate unions. Their **129 three-view numerical states** and saved objective/NLL/KKT values are exactly equal, with maximum differences zero. Elapsed times differ because the control executed fresh fits. This supports unchanged common-point numerical behavior; it is not proof of global optimality or universal accuracy improvement.

The control terminal SHA-256 is `0228a7dc563f84ff37562ef920e55616413dd3f787bad9756721c73aafec360a`. The [original DS21-009 three-model results](THREE_MODEL_009_RESULTS.md) remain unchanged. Any downstream comparison must use the qualified initialization/model adapters and seal all required outcomes before reference evaluation. Half-view likelihoods inherit shared discovery and initialization; the configured reference is not independently surveyed ground truth. No reference ranking, reference-derived seed, zero-c run, tolerance change or retry was introduced. Locked inference remains unopened, and the full-DS21 0.5 km target remains unmet.
