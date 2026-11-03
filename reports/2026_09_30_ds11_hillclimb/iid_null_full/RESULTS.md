# Original IID plus linear-trend null screen

The q000 control reproduced the original IID objective exactly at the original index-0 endpoint: score and all three gradient components were identical, the optimized score differed by `2.55e-11`, and the largest endpoint-coordinate difference was `8.88e-9`. This establishes the full-catalogue-divisor control before testing a nonzero null prior.

All 24 declared screen fits terminated successfully within the 90-second cap. All 24 selected endpoints also passed the independent scientific audit. Effective signal weight ranged from 55.1 to 62.8 tracks, every observed-information matrix was positive definite, and the smallest timing-profiled horizontal eigenvalue was 3.91 km^-2 versus the predeclared 1/144 km^-2 minimum. The results therefore are not flat all-null endpoint artifacts.

| Variant | Numerical | Scientific | Median (baseline 3108 m) | P90 (baseline 6046 m) | Wins | Advance |
|---|---:|---:|---:|---:|---:|---:|
| q005 | 8/8 | 8/8 | 3433 m (+10.5%) | 6081 m (+0.6%) | 2/8 | no |
| q020 | 8/8 | 8/8 | 3409 m (+9.7%) | 6147 m (+1.7%) | 2/8 | no |
| q050 | 8/8 | 8/8 | 3394 m (+9.2%) | 6208 m (+2.7%) | 2/8 | no |

Every arm fails the paired-win, median-improvement, and nonworse-P90 conditions. No variant is selected, and the protocol permits no remaining-24 or additional-12 fits from this family. The detailed machine-readable control, numerical, information, and gate results are in `screen-summary.json`; per-endpoint information records remain under `information/wave1/`.
