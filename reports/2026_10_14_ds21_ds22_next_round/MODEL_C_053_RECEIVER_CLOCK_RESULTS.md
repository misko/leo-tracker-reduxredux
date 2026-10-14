# C053 receiver clocks reverse the wrong-region selection

In a matched four-fit pilot, adding the existing zero-affine receiver-clock spline design changed the selected C053 endpoint from 253.901882 km error to 10.055802 km error. Both original and clock-enabled models received the same two training-selected union-bank endpoints, their own original 25 km disks, and 20-second/600-iteration budgets per fit. All four fits passed the unchanged stationarity checks.

| Model | Endpoint origin | Objective | NLL | Prior | Development error km |
|---|---|---:|---:|---:|---:|
| Original | Later/incumbent, selected | 24198.937767 | 23795.014143 | 403.923624 | 253.901882 |
| Original | Earlier/shifted | 24318.889225 | 24031.517341 | 287.371884 | 9.597334 |
| Receiver clock | Later/incumbent | 23992.470160 | 23523.756057 | 468.714103 | 253.805010 |
| Receiver clock | Earlier/shifted, selected | 23693.894241 | 23351.163301 | 342.730940 | 10.055802 |

Within the original model, the closer endpoint loses by 119.951458 objective units. Within the expanded model, it wins by 298.575919: NLL is 172.592756 better and prior penalty is 125.983163 smaller. This is a successful correction of the region selected in this pilot. It is not sub-kilometer positioning, and the closer endpoint's own error slightly worsens from 9.597334 to 10.055802 km. The selected-error improvement must therefore be distinguished from local position refinement.

The extension preserves the original native likelihood, candidate bank, receiver lift, group calibration, observations and orbit nodes. It uses the existing receiver-clock curvature prior with scale four; there was no prior tuning in this experiment. At zero clock coefficients, both endpoints reproduced objective, NLL, existing gradients, satellite responsibilities and clutter probabilities exactly (all measured deltas zero). Both initializers remained unprojected and inside their original allowed domains.

The original incumbent remained eligible in the original arm; the clock arm selected only among new accepted fits. Reference coordinates were joined after all four outcomes and their training selections were sealed. This remains a repeatedly inspected development pilot with additional endpoint-start fit cost, not a promoted full-cohort estimator. The earlier C029 clock pilot did not repair selection, so this result does not establish a universal fix.

Runtime 55.650 seconds: four qualification objective evaluations and four optimizer calls. Stationarity values in table order were 3.527e-5, 5.324e-4, 5.955e-5 and 9.770e-5. Component tests cover exact zero-clock nesting and added-clock finite differences, four matched calls, preserved original fallback, rejection retention, no retry and blocked premature reference access. All three relevant tests and Ruff passed. Research commit `3c0c18ffa`.

Output `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-c-winner-clock-053-v1/`. Terminal SHA256 `dcc4bec9c76c445c34415a50014c3b86681e0060f3daca8a0e3d7a9ec6dc7ab3`; seal SHA256 `884164a0566f4413070adcb8c5dbbc13fdfcbf253f825c52c8c2ef9439da71d6`.

Next: audit which channel/receiver assignment changes produce the clock-enabled selection reversal, then test comparable low-only/high-only fits and additional genuine starting points. The goal remains that full-band accuracy beat both halves and achieve a median below 0.5 km across DS21 and DS22.
