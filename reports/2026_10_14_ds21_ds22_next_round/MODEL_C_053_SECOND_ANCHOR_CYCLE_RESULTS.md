# C053 second anchor cycle: better objective, worse position

One further matched profile/release cycle finds a lower full-band objective
but worsens selected error from1.027646 to1.419297 km. This is a negative
localization result, retained without choosing the older state by reference.
All six new fits pass independent KKT checks. The original incumbent remains
eligible but loses the training-objective selection.

| Training anchor | Fixed profile objective | Released objective | Released error (km) |
|---|---:|---:|---:|
| Full | 22314.652881 | 22314.652881 | 1.027646 |
| Low | 22314.796957 | 22314.652881 | 1.027645 |
| High, selected | 22289.367798 | 22288.344962 | 1.419297 |

The high anchor is the0.724527 km half-band fit from the preceding matched
experiment; it was selected by its own training objective, not reference error.
At this fixed position the reprofiled full NLL is22065.031881 and prior224.335917.
Releasing position reduces NLL by0.474899 and prior by0.547938, a total objective
gain of only1.022837, while increasing reference error. The released selected
endpoint is interior at radius35.909439 km, KKT0.000017360. This suggests weak
or biased local geographic discrimination, but does not by itself identify
which likelihood or prior assumption is responsible.

Every anchor starts from the same current full-band calibration and timing
parameters. Profiles fix only geography; accepted profiles are released in the
original common50 km disk. Each fit has20 seconds/600 iterations, with no retry
or altered prior. Six calls were sealed before reference evaluation; runtime
61.480 seconds. Four tests across driver/evaluator and Ruff pass.

Further identical anchor cycles are not justified without new evidence. Next
diagnostics should separate per-channel likelihood and physical timing/clock
prior contributions around these sealed states, rather than select a model or
prior strength using the known reference position.

Driver `d8f0fc532`, evaluator `730152898`.
Namespace `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-c-released-anchor-cycle-053-v1`.
Terminal SHA256 `79dd38bbbbab63fa3489ae5d58addabd01d52a05cd4191856ead046d8f95143f`.
Seal SHA256 `bb8fe076348713c19f5fb415f56eebad45f2d601969824eeb50bb5f4581586d7`.
