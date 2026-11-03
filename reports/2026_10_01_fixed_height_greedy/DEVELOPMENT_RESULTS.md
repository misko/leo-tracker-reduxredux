# Sealed development results

| unit | arm / variant | status | error m | iterations | runtime s |
|---|---|---:|---:|---:|---:|
| DS10-F001 | fixed_height_beam1 / height-extended-v3 | complete | 312065.9 | 44 | 10.738 |
| DS11-F001 | fixed_height_beam1 / height-extended-v3 | complete | 306153.7 | 48 | 11.687 |
| DS10-F001 | fixed_height_beam1 / height-only-v1 | error | 286916.9 (failed diagnostic) | 4 | 6.168 |
| DS11-F001 | fixed_height_beam1 / height-only-v1 | error | 291616.3 (failed diagnostic) | 43 | 11.041 |
| DS9-F001 | fixed_height_beam1 / height-only-v1 | complete | 264270.4 | 50 | 11.653 |
| DS11-F001 | joint / joint-t4-v3 | converged_local_mode | 1628.2 | 12 | 58.683 |
| DS10-F001 | joint / joint-v1 | converged_local_mode | 218377.5 | 10 | 41.786 |
| DS9-F001 | joint / joint-v1 | converged_local_mode | 1326.4 | 6 | 28.358 |
| DS10-F001 | joint / joint-v2 | converged_local_mode | 25621.9 | 11 | 23.459 |
| DS11-F001 | joint / joint-v2 | converged_local_mode | 9835.3 | 8 | 53.808 |

Numerical convergence and roof-reference error are separate fields. Failed point errors are diagnostic only. The future panel denominator is 64; this table is not a publication claim.
