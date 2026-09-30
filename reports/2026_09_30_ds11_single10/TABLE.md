# DS11: ten methods on 32 independent scans

Distances are metres to the unsurveyed roof reference. Failure cells remain in attempted denominators. Each scan is fitted independently.

| Method | Qualified | Median m | P90 m | Min m | Max m | <1 km / attempted | Matched median m | Runtime s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Original independent Student-t | 32/32 | 2759 | 7708 | 765 | 8540 | 2/32 | 2759 | 24.78 |
| q020 + shared curvature | 32/32 | 3364 | 8059 | 706 | 9336 | 2/32 | 3364 | 5.83 |
| Shared scale | 32/32 | 3476 | 7462 | 884 | 9398 | 1/32 | 3476 | 2.81 |
| Shared scale + 40° cones | 32/32 | 3481 | 7465 | 886 | 9405 | 1/32 | 3481 | 4.17 |
| Frequency contrasts | 32/32 | 3491 | 7456 | 858 | 9399 | 1/32 | 3491 | 2.41 |
| Shared scale + 10 s correlation | 32/32 | 3564 | 7389 | 195 | 9619 | 3/32 | 3564 | 2.51 |
| q020 + shared candidate slope | 32/32 | 3678 | 7999 | 1000 | 8654 | 1/32 | 3678 | 5.48 |
| q020 + 10 s correlation | 32/32 | 3714 | 7217 | 170 | 9291 | 3/32 | 3714 | 2.86 |
| q020 | 32/32 | 3759 | 8000 | 1038 | 9342 | 0/32 | 3759 | 2.36 |
| q020 + 40° cones | 32/32 | 3837 | 8018 | 1009 | 9345 | 0/32 | 3837 | 4.71 |

Matched medians use the 32 scans qualified by all ten methods. Runtime includes q020 prerequisites for slope and curvature; engineering retries are separately retained.

## All selected scans

Column names are method IDs in [run.py](run.py). Unqualified or failed cells are printed as status, not zero.

| Scan / chronological rank | iid | shared | correlated | contrast | q020 | q020_correlated | cone40 | q020_cone40 | slope | curvature |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| S01 / 1 | 765 | 1699 | 1177 | 1708 | 1708 | 1165 | 1671 | 1705 | 1771 | 1880 |
| S02 / 3 | 2476 | 5543 | 4009 | 5539 | 5542 | 3983 | 5545 | 5560 | 5340 | 5207 |
| S03 / 6 | 2498 | 2186 | 2901 | 2193 | 2224 | 2922 | 2200 | 2240 | 2223 | 2504 |
| S04 / 9 | 2313 | 1311 | 3468 | 1309 | 1280 | 3444 | 1291 | 1224 | 1471 | 1314 |
| S05 / 12 | 3510 | 4897 | 5872 | 4833 | 4329 | 4424 | 4928 | 4341 | 4130 | 4210 |
| S06 / 14 | 2108 | 1377 | 1939 | 1380 | 1423 | 2034 | 1377 | 1421 | 1362 | 1456 |
| S07 / 17 | 959 | 1078 | 761 | 1075 | 1075 | 829 | 1084 | 1074 | 1000 | 1146 |
| S08 / 20 | 8540 | 8205 | 6051 | 8215 | 8177 | 6070 | 8209 | 8491 | 8175 | 8299 |
| S09 / 23 | 5271 | 5234 | 5045 | 5226 | 5273 | 5060 | 5226 | 5291 | 5208 | 5274 |
| S10 / 25 | 7345 | 9398 | 7430 | 9399 | 9342 | 6634 | 9405 | 9345 | 8654 | 9336 |
| S11 / 28 | 2046 | 3776 | 3401 | 3779 | 3737 | 3291 | 3776 | 3741 | 3756 | 2746 |
| S12 / 31 | 6844 | 2515 | 4072 | 2515 | 2534 | 4176 | 2516 | 2531 | 2639 | 2412 |
| S13 / 34 | 1184 | 1485 | 492 | 1488 | 1578 | 626 | 1567 | 1661 | 1506 | 1645 |
| S14 / 37 | 3410 | 3396 | 4193 | 3407 | 3782 | 4910 | 3440 | 4323 | 3971 | 8214 |
| S15 / 39 | 1865 | 3493 | 1740 | 3497 | 3472 | 1759 | 3480 | 3462 | 3437 | 3318 |
| S16 / 42 | 1361 | 1505 | 1765 | 1494 | 1571 | 1795 | 1506 | 1561 | 1605 | 706 |
| S17 / 45 | 2153 | 1675 | 3420 | 1682 | 1757 | 3377 | 1678 | 1771 | 1653 | 1775 |
| S18 / 48 | 2180 | 1993 | 3659 | 2008 | 2129 | 4166 | 1997 | 2096 | 2084 | 2015 |
| S19 / 50 | 1060 | 1947 | 1898 | 1952 | 2061 | 1642 | 1952 | 2067 | 2127 | 2136 |
| S20 / 53 | 1090 | 884 | 195 | 858 | 1038 | 170 | 886 | 1009 | 1062 | 863 |
| S21 / 56 | 2706 | 6386 | 5456 | 6373 | 6395 | 5284 | 6423 | 6404 | 6406 | 6976 |
| S22 / 59 | 4393 | 3931 | 3386 | 3931 | 3917 | 3348 | 3943 | 3933 | 3599 | 4177 |
| S23 / 62 | 2813 | 3428 | 7406 | 3460 | 3224 | 7520 | 3429 | 3216 | 3393 | 2385 |
| S24 / 64 | 3579 | 3954 | 4507 | 3940 | 3963 | 4616 | 3954 | 3976 | 4030 | 3410 |
| S25 / 67 | 5918 | 7515 | 4903 | 7510 | 8109 | 4891 | 7519 | 8152 | 8102 | 8068 |
| S26 / 70 | 3174 | 8028 | 1162 | 8013 | 8125 | 1452 | 8030 | 8132 | 8272 | 7969 |
| S27 / 73 | 7749 | 3460 | 2569 | 3484 | 4198 | 3388 | 3481 | 4298 | 4289 | 4311 |
| S28 / 75 | 1783 | 2934 | 1233 | 2943 | 3279 | 1553 | 2941 | 3380 | 3186 | 2812 |
| S29 / 78 | 6346 | 6396 | 6688 | 6391 | 6466 | 6812 | 6398 | 6469 | 6699 | 6292 |
| S30 / 81 | 7321 | 6901 | 7637 | 6912 | 6890 | 7524 | 6900 | 6925 | 7074 | 6401 |
| S31 / 84 | 8308 | 6981 | 7241 | 6975 | 7020 | 7262 | 6983 | 6989 | 6984 | 6862 |
| S32 / 87 | 8052 | 5355 | 9619 | 5293 | 5155 | 9291 | 5369 | 5056 | 5256 | 4830 |

## Frozen scan membership

| Scan | DS11 rank | Session | MS/s |
|---|---:|---|---:|
| S01 | 1 | scan-fw-a32c07775a887379 | 5 |
| S02 | 3 | scan-fw-1104f08bdc373471 | 10 |
| S03 | 6 | scan-fw-49d3aae278813149 | 7.5 |
| S04 | 9 | scan-fw-40342f486cccc9d9 | 10 |
| S05 | 12 | scan-fw-6575ab4394ce18d4 | 5 |
| S06 | 14 | scan-fw-c3b376fb262f4d2e | 10 |
| S07 | 17 | scan-fw-57637a9113e75330 | 10 |
| S08 | 20 | scan-fw-f1e2c050ac43a181 | 7.5 |
| S09 | 23 | scan-fw-9002e33591f2f60b | 10 |
| S10 | 25 | scan-fw-e3b6d5e4216285b4 | 5 |
| S11 | 28 | scan-fw-b5b7bdee0eec6b5d | 10 |
| S12 | 31 | scan-fw-bdebca84c993a39f | 10 |
| S13 | 34 | scan-fw-3773a5de2cae9212 | 10 |
| S14 | 37 | scan-fw-366335f256f0e364 | 10 |
| S15 | 39 | scan-fw-86b8d833a818f08f | 7.5 |
| S16 | 42 | scan-fw-7aa0a593f8f8e233 | 2.5 |
| S17 | 45 | scan-fw-6a8bd0ca578b58eb | 5 |
| S18 | 48 | scan-fw-57af4c0ef8089db5 | 10 |
| S19 | 50 | scan-fw-682838e4169fa032 | 5 |
| S20 | 53 | scan-fw-0bcf99ca2b158c2c | 5 |
| S21 | 56 | scan-fw-61be64a021e343e8 | 5 |
| S22 | 59 | scan-fw-4dbf1fb13ad2ed54 | 7.5 |
| S23 | 62 | scan-fw-47639950dbd07a0f | 5 |
| S24 | 64 | scan-fw-2ce4bf27b97e1a83 | 10 |
| S25 | 67 | scan-fw-40ae60052a6435ae | 2.5 |
| S26 | 70 | scan-fw-2a60591f680cd8c2 | 10 |
| S27 | 73 | scan-fw-f7f4568e8daa4db4 | 7.5 |
| S28 | 75 | scan-fw-5d2e9ba7479fde9d | 10 |
| S29 | 78 | scan-fw-12673ffd4ab77b65 | 10 |
| S30 | 81 | scan-fw-09398d404640c2d6 | 5 |
| S31 | 84 | scan-fw-aa0c324dd1825b44 | 2.5 |
| S32 | 87 | scan-fw-8165310e3c4e205a | 2.5 |

## DS10 versus DS11

These are different scan populations (8 versus 32), not paired measurements of improvement. Methods and fit settings are unchanged.

| Method | DS10 median m | DS11 median m | DS10 P90 m | DS11 P90 m |
|---|---:|---:|---:|---:|
| Original independent Student-t | 2009 | 2759 | 5128 | 7708 |
| Shared scale | 1938 | 3476 | 5213 | 7462 |
| Shared scale + 10 s correlation | 1423 | 3564 | 4318 | 7389 |
| Frequency contrasts | 1953 | 3491 | 5213 | 7456 |
| q020 | 2347 | 3759 | 5212 | 8000 |
| q020 + 10 s correlation | 1363 | 3714 | 4407 | 7217 |
| Shared scale + 40° cones | 1943 | 3481 | 5189 | 7465 |
| q020 + 40° cones | 2359 | 3837 | 5170 | 8018 |
| q020 + shared candidate slope | 2449 | 3678 | 5277 | 7999 |
| q020 + shared curvature | 2100 | 3364 | 5499 | 8059 |

## Common held-observation diagnostic

All fitted points are scored by the same q020 held model. These are not native cross-model likelihoods or independent future-scan tests.

| Method | Sum held-score change versus q020 | Paired scans |
|---|---:|---:|
| Original independent Student-t | -853.486 | 32 |
| Shared scale | 0.593 | 32 |
| Shared scale + 10 s correlation | -885.485 | 32 |
| Frequency contrasts | 0.258 | 32 |
| q020 | 0.000 | 32 |
| q020 + 10 s correlation | -854.020 | 32 |
| Shared scale + 40° cones | 3.158 | 32 |
| q020 + 40° cones | 1.825 | 32 |
| q020 + shared candidate slope | -22.274 | 32 |
| q020 + shared curvature | -82.100 | 32 |
