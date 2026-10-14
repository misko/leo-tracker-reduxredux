# C053: training-anchor calibration profiling finds a better full-band basin

Full-band error improves from 1.749188 to **1.027646 km** after calibration
profiling at three training-derived positions and geographic release. The new
full-band result is better than the preceding conditional half-band errors
(low 1.405833 km; high 1.759683 km), but remains above 1 km. This is an extended
search pilot with six additional full-band fits, not a matched-budget cohort
improvement. The original histogram and cohort results are unchanged.

All three fixed-position profiles initialize every non-position parameter from
the same full-band endpoint. Position is taken from the sealed full, low, or
high 50 km fit, never from reference data. All profiles use the full likelihood,
unchanged candidate bank, receiver clock model, fitted c and priors, 20 seconds
and 600 iterations. All three pass independent fixed-position KKT checks.

| Training position | Profile objective | Profile NLL | Profile prior | KKT |
|---|---:|---:|---:|---:|
| Full | 22885.711905 | 22639.385952 | 246.325953 | 0.000168297 |
| Low | 22886.180221 | 22640.070855 | 246.109365 | 0.000021068 |
| High | 22347.829969 | 22109.100451 | 238.729518 | 0.000403586 |

The low geographic position is nearly tied with the original full optimum
after nuisance refitting (objective +0.468315). The high position accesses a
substantially lower calibration basin (objective −537.881936). Thus the large
cross-view losses in the earlier raw endpoint-transfer audit were not a valid
geographic preference test.

Every accepted profile is then released using the same original discovery
centre and 50 km disk, 20 seconds and 600 iterations. Original full incumbent
remains eligible. Training objective selection is sealed before reference join.

| Profile origin | Released objective | Released NLL | Error (km) | KKT |
|---|---:|---:|---:|---:|
| Full | 22885.711905 | 22639.385952 | 1.749188 | 0.000499852 |
| Low | 22885.711905 | 22639.385953 | 1.749188 | 0.000008187 |
| High, selected | 22314.652881 | 22083.543077 | 1.027646 | 0.000105388 |

All three releases pass; selected radius35.543162 km is interior to the 50 km
disk. The result improves both full objective and post-seal accuracy, but no
claim of global optimality or performance below0.5 km is supported.

Profile runtime37.863 seconds; release runtime30.543 seconds. Component tests
cover common nuisance preservation, failed-profile exclusion, unchanged release
domain, incumbent retention and rejection of invalid pre-reference selections.
Five tests across the three new components and Ruff passed.

Source commits: profile `a9018bf75`, release `0bd71ffcf`, evaluator `9e8056f62`.
Bulk parent: `/srv/bulk/leo-research-ds21-ds22/2026_10_14`.
Profile namespace: `model-c-expanded-anchor-profile-053-v1`.
Profile terminal SHA256 `e7a86da6af25a813da7c9e481dd1454c76eb0947505cd044dcdc274aa608a1b2`.
Release namespace: `model-c-expanded-anchor-release-053-v1`.
Release terminal SHA256 `bbe9cb2945fbaaeccd056424ce103555d3b582fc1ce3ec1c935918e7b1c4d4fb`.
Release seal SHA256 `3151b8f770d56f975d5836c40df4b963fc4d4c84cd16b5935029c11cb69ff70c`.
