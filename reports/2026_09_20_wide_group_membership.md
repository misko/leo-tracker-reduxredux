# Exact membership of the wide-position sensitivity groups

These are deterministic deletion experiments on the previously selected historical September 7 cohort, not detected bad-data classes. Each fit retains all other selected data. The reported full-data result retains every group and has 940.8 m spherical horizontal error. Satellite identities and the parent quality selection remain frozen; these are sensitivity experiments rather than independent validation or causal fault attribution.

Satellite group k contains every observation assigned to a NORAD identifier whose remainder after division by eight is k. Recording groups use the parent extraction recording index modulo eight; they are interleaved across the day, not contiguous time blocks.

## Satellite groups

| Group | Assigned NORAD IDs removed | Episodes removed | Observations removed | Resulting error (m) |
|---|---|---:|---:|---:|
| 0 | 57736, 58552, 59016, 59328, 59360, 62032, 62104, 62208, 62280, 63480, 65696, 66496, 67352, 69752 | 14 | 809 | 935.8 |
| 1 | 51801, 58745, 59497, 59873, 62601, 63577, 64209, 67913, 67921, 68081, 69257, 69945 | 12 | 640 | 1147.8 |
| 2 | 58210, 58242, 58386, 58410, 58546, 58738, 58874, 59314, 61866, 63466, 64106, 64498, 64674, 65090, 67082, 67346, 67514, 67826, 67914 | 20 | 1153 | 1228.0 |
| 3 | 57907, 57931, 60107, 61723, 62211, 63579, 66835, 69451 | 8 | 330 | 1044.3 |
| 4 | 58604, 60020, 62604, 64804, 68340 | 5 | 260 | 1036.5 |
| 5 | 58029, 59309, 59733, 62037, 62053, 63805, 64733 | 7 | 477 | 877.0 |
| 6 | 58798, 60286, 65102, 65894, 66334, 66446, 66542, 67214, 67406 | 10 | 652 | 1024.7 |
| 7 | 58999, 59079, 63463, 64479, 64687, 66119, 66863, 67359, 67847, 68055 | 10 | 468 | 879.7 |

## Recording groups

Times are first-sample UTC on 2026-09-07. A recording with no episodes surviving the frozen quality selection contributes no removed observations.

| Group | Recordings removed | Episodes removed | Observations removed | Resulting error (m) |
|---|---|---:|---:|---:|
| 0 | 08:03:00 `scan-hop-66cae29c39756be7`; 10:40:05 `scan-hop-fc2894f68f081fdb`; 13:20:05 `scan-hop-4c70b4f8bb61dd9c` | 13 | 714 | 1043.2 |
| 1 | 11:00:05 `scan-hop-6c9417eeec67a616`; 13:40:05 `scan-hop-92528c5e4fdebe62` | 9 | 530 | 999.7 |
| 2 | 08:40:04 `scan-hop-9ab159ed70a6797d`; 11:20:06 `scan-hop-9727ae34eed5fe0e`; 14:00:06 `scan-hop-3a957b05cd511170` | 9 | 359 | 1019.1 |
| 3 | 09:00:05 `scan-hop-1de0e88e6d9453ba`; 11:42:56 `scan-hop-17cd3d70f957353e`; 14:20:05 `scan-hop-d04702aa7553ee39` | 12 | 750 | 1013.2 |
| 4 | 09:20:51 `scan-hop-fa8b9ec97ff14b97`; 12:00:05 `scan-hop-5ce35ea0172e21d4`; 14:40:06 `scan-hop-6852fe2076fb7caf` | 18 | 1017 | 998.8 |
| 5 | 09:40:05 `scan-hop-740375254f7d3eb3`; 12:22:49 `scan-hop-8a67fa6d0e7c4d21`; 15:01:30 `scan-hop-5187ef22966d304c` | 7 | 406 | 888.7 |
| 6 | 10:00:04 `scan-hop-ed5f119bec16d845`; 12:40:04 `scan-hop-163ca5acea5cce6b`; 15:20:04 `scan-hop-327e2a741379baec` | 8 | 444 | 986.2 |
| 7 | 10:23:00 `scan-hop-04f15d400cc34fd7`; 13:00:05 `scan-hop-4bbb02e1f0dda66b`; 15:40:05 `scan-hop-7a31f1dfb82a20e3` | 10 | 569 | 966.2 |

## What a future device can detect

A future device can measure disagreement, association ambiguity, clock-bound pressure, timing integrity, catalogue age, residual structure, and how much the inferred position moves when each independent pass is removed. It cannot know whether that movement is toward the true location without an external reference. High influence can mean useful geometric information, a biased measurement, or both. Modulo group membership is never an exclusion rule.

A reliable exclusion policy requires a fault signature or a rule validated on other recordings/locations, with position uncertainty accounting for residual correlation and loss of geometric diversity. Better error after a retrospective deletion is not that validation.

Source audit SHA-256: `12564bbcbcbf11f02b0ca7348c8feadbfa5a2e3166220b883652874a5c2e45c8`. Distances are evaluated after inference against the user-supplied antenna reference with spherical radius 6,371,008.8 m.

[Parent report](2026_09_20_wide_session_clocks.md)
