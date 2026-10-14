# Native C union: likelihood and convergence are separate problems

The fixed-endpoint diagnostic completed all 24 objective evaluations, 24 explicit orbit predictions and 48 band-likelihood evaluations in 26.90 s, with zero fits and no reference reads. It replays every sealed endpoint, accepted or rejected, and verifies stored objective/NLL and additive band-NLL closure within 1e-7. Endpoint error labels below come only from the already sealed retrospective evaluation.

| Case / endpoint | Accepted | Low NLL | High NLL | Low signal mass | High signal mass |
|---|---|---:|---:|---:|---:|
| 029 selected broader start 0 (83.39 km) | yes | 18665.865 | 14097.779 | 960.995 | 796.491 |
| 029 broader start 1 (5.20 km) | yes | 21979.037 | 16137.255 | 458.666 | 495.175 |
| 035 selected original start 0 (48.70 km) | yes | 21824.758 | 14930.043 | 1098.178 | 793.178 |
| 035 original start 4 (9.78 km) | no | 19958.283 | 13567.522 | 1356.722 | 996.430 |
| 035 original start 5 (10.86 km) | no | 20680.658 | 13713.533 | 1224.107 | 962.294 |

Both bands prefer the inaccurate 029 winner under these fitted states. For 035, both bands prefer the lower-error rejected endpoints, but their large stationarity residuals still disqualify them. These observations support distinct investigations of likelihood basins and numerical convergence; they do not justify changing acceptance thresholds.

## Discrete receiver ambiguity is a new confound to test

Inspection of the saved 029 initialization metadata reveals that broader start 0 used receiver ambiguity integers `(-1,+2)`, while start 1 used `(-1,+1)`. Receiver 1's modal support was 228 confident windows with fraction 0.728070 for start 0, versus 73 with fraction 0.547945 for start 1. Their fitted receiver-1 offsets are 472187.495 and 247382.500 Hz, separated by approximately one 227272.727 Hz OFDM ambiguity interval. Receiver-0 integers agree.

This is an observed difference, not proof that an ambiguity choice causes the position error. Geography, calibration and satellite timing also differ. The next diagnostic should hold every sealed endpoint fixed and evaluate the same declared receiver-integer neighborhood across all twelve endpoints, without choosing states by reference distance. That can reveal whether discrete ambiguity search is missing useful native-likelihood basins before any new fit is proposed.

Source: `94d2c4ad9`; actual native probability/NLL closure test and Ruff pass. Evidence: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-c-union-band-audit-v1`. Result SHA256 `3492b0622884c42dd89c8408530ba978c996f511c86e06bb533a6b9710562dfd`; seal SHA256 `c62c2bd6369ff698c30ae03a4d24b240055428a8324ffe89d3d124013429aff9`. Candidate counts, observations, native branches, correction frames, physical priors and the original conditional likelihood remain unchanged.
