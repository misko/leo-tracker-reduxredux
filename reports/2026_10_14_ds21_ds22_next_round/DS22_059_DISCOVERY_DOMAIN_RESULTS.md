# DS22-059: configured station excluded by every final search disk

The post-seal coverage check shows that the configured station is inside the 250 km original prior but outside every one of the six final 25 km search disks. In the actual original optimization coordinates, it is 118.889651 km from the prior center and 137.281206 km from the nearest final disk center: a 112.281206 km miss beyond that disk's radius. This is conditional on the unconfirmed DS22 configured station reference.

| Start | Configured point to disk center km | Inside 25 km disk? |
| --- | ---: | --- |
| 0 | 306.010824 | No |
| 1 | 322.384731 | No |
| 2 | 268.580690 | No |
| 3 | 368.309478 | No |
| 4 | 211.543484 | No |
| 5 | 137.281206 | No |

This corrects the potential inference from interior fitted winners: their interior status does not rule out exclusion of another basin by discovery. No reference coordinate was used to change a seed, candidate, ranking or fit. The domain check used a tested inverse of the original spherical local-coordinate mapping and joined the reference only after the original matrix and metadata inventory were sealed.

A separate reference-free audit read all 100 original cold-discovery point receipts. The original search stopped at its point budget with 85 deferred cells. The top initial coarse scores were:

| Coarse point east/north km | Training score | Point candidates present in final 50 |
| --- | ---: | ---: |
| 50, 150 | 44994.871961 | 22/22 |
| -50, 50 | 46392.269934 | 18/20 |
| 50, 50 | 47371.594967 | 21/23 |
| 150, 150 | 47705.590791 | 24/25 |

Every initial coarse full-view fit converged. The final cold selector first takes the low, high and full-view training winners, deduplicates at 12.5 km, then fills from full-score ranking. Both half winners coincided at (106.25,156.25), whose full score was 50539.110024. The full winner was (131.25,156.25), score 44133.951560; the third proposal was the full-score fallback (50,150). Thus both half rankings also concentrated cold proposals in the northeast; the clustering is not solely a full-view ranking artifact. Three shape-derived proposals completed the original six starts.

The (-50,50) alternative ranked second among coarse points and seventh among all 100 full scores, but was not retained among the final cold proposals. Candidate overlap is substantial but incomplete: across the coarse grid it ranges from 11/17 to 24/25. These facts motivate a prospective training-only coverage policy that preserves existing starts and candidates when adding basins. They do not establish which basin or satellites are correct, and no such new fit was launched by these diagnostics.

Wrapped discovery receiver offsets cannot identify native integer-alias representatives. The weak native lift modes recorded at the final six starts remain a separate diagnostic concern. C-all's six nonstationary endpoints remain another distinct failure; no acceptance rule or result was changed.

Sources: `ed307c29c` (post-seal domain coverage; four roundtrip tests), `cd3b9d454` (all-point training inventory; component test), Ruff clean. Both diagnostics made zero objective evaluations and zero fits. Evidence namespaces under `/srv/bulk/leo-research-ds21-ds22/2026_10_14`: `ds22-059-domain-comparison-v1` and `ds22-059-discovery-inventory-v1`.
