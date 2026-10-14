# C053 fixed channel offsets: limited gain and one unresolved boundary

Both sealed union-bank endpoints were evaluated on the same −1000 to +1000 Hz grid in 50 Hz increments. Geography, satellite timing, original calibration and candidate bank remained fixed. Every channel and receiver/channel group was retained; diagnostic offsets have no prior penalty. This is a frequency-likelihood sensitivity test, not a new fitted position estimate.

| Endpoint | Original NLL | Sum of independent channel gains | Sum of independent receiver/channel gains |
|---|---:|---:|---:|
| Earlier/closer | 24031.517341 | 18.358501 | 70.572273 |
| Later/distant | 23795.014143 | 1.044329 | 11.712568 |

The original NLL gap of 236.503198 shrinks to 219.189026 with channel-only offsets or 177.643492 with receiver/channel offsets. Holding the original prior penalties fixed, the latter would still leave the closer endpoint 61.091752 objective units worse. These profiled alternatives are not promoted estimators and do not improve the reported localization metric.

There is one important unresolved search boundary: earlier-endpoint RX1/CH4 chooses −1000 Hz, improving NLL by 38.9147. It is the only group whose minimum lies at a grid edge. This prevents concluding that independent constant offsets are insufficient over a wider range. At the distant endpoint RX1/CH4 chooses +50 Hz with only 0.1034 improvement. The earlier assignment audit found this group contributed +361.493 NLL against the closer endpoint, so the present bounded grid recovers only part of that discrepancy.

A next diagnostic can widen the prespecified grid symmetrically for both endpoints and all groups, retaining the original result. This is motivated by the measured boundary, not by reference-coordinate tuning. A wider grid must still distinguish a calibration correction from an offset that simply admits a different satellite association.

Validation: both saved objectives and zero-offset NLLs replay within 1e-7. The actual native-objective component test checks both complete 41-point grids, identical results for identical states, and no retry. Ruff passed. Research commit `0c8d8485a`.

Runtime 10.273 seconds; two objective evaluations, two explicit orbit calls, 82 grid likelihood evaluations, zero optimizer calls. Output `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-c-winner-channel-053-v1/`. Result SHA256 `1fd635e7202e488abdbe51e42f78d971b0b4d2376fce679f8ddefbb2b20cb5ff`; seal SHA256 `b6ab971ec94f7c1f2b152643c96039f83dab8e63d0ce727d00f6b2f542cfbf63`.
