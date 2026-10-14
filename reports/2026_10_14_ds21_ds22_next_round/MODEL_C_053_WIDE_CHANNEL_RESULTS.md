# C053 wider offset grid does not reverse the score preference

The measured RX1/CH4 boundary from the original ±1 kHz profile triggered a new, separately frozen ±5 kHz profile in 50 Hz increments. Both original sealed union endpoints and all channel/receiver groups were retained. Positions, satellite timings and original calibration remained fixed. The original artifacts were not changed.

| Endpoint | Independent channel NLL gain | Independent receiver/channel NLL gain |
|---|---:|---:|
| Earlier/closer | 18.358501 | 122.559077 |
| Later/distant | 1.044329 | 89.140262 |

The closer endpoint's RX1/CH4 minimum is now interior at −1300 Hz, with NLL gain 88.333436. However, the distant endpoint also gains 87.428807 on RX1/CH3 at +1750 Hz. No group optimum remains at the wider grid boundary. All values at the original 41 grid points reproduce exactly for every group and both endpoints.

The original closer-minus-distant NLL gap of 236.503198 becomes 203.084383 after independent receiver/channel profiling. With the original prior penalties unchanged and no penalty on diagnostic offsets, the closer endpoint still loses by 86.532643 objective units. Channel-only gains are unchanged from the narrower grid. The wider search therefore weakens the constant-offset explanation rather than establishing a localization fix. It cannot exclude time-varying calibration mismatch or offsets outside the measured range, and these alternative frequency fits are not new position estimates.

The two profiles used 402 grid likelihood evaluations, two objective evaluations, two explicit orbit calls and zero optimizer calls, completing in 18.068 seconds. Component testing covers the complete enlarged grids, preservation of original grid coordinates, identical-state agreement, and no retry. Source commit `753fc2d68`. Ruff identified one 106-character CLI dispatch line (E501); the frozen source is retained unchanged. This formatting issue does not affect the numerical result; no claim of a clean Ruff run is made for this version.

Output: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-c-winner-channel-053-v2/`. Result SHA256 `52901ef52678a13231e34912f10fbb9e48e959633f368c8776b29627cf871420`; seal SHA256 `e40b1c9c89ace6bbacd877cdb26cb6d98f67779bf2239bce2489986f1955f2bd`.

No model is promoted. The next controlled C053 model comparison should distinguish time-varying receiver calibration from the original plain native model, using the existing zero-affine receiver-clock design, both training-selected endpoints, identical fit budgets and unchanged acceptance tests. Better likelihood alone will not count as improved localization.
