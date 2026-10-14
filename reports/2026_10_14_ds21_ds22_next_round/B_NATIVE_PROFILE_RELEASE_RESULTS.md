# Native profile-then-release control

Releasing the accepted native-C profile at B's training-selected geography reaches a new lower stationary objective, but again moves away from B's configured-reference location. This final movement is driven mainly by reduced prior penalty, with a smaller likelihood improvement.

Source `8c83de949` binds the complete crossed-state diagnostic, including its failed profiles, and starts exactly from the accepted B-geography profile. It performs one new free fit in the original B-winning disk: fitted c, 20 seconds, at most 600 actual objective evaluations across the original solver and optional strict gradient finish. No failed crossed fit was retried, no seed was selected by reference distance, and no held observations were read.

| State | Objective | NLL | Prior penalty | Configured-reference distance, km |
|---|---:|---:|---:|---:|
| Accepted fixed B-geography profile | 40153.718553 | 39727.186565 | 426.531988 | 0.785018 |
| Free release from that profile | 40105.323209 | 39721.093124 | 384.230085 | 5.582157 |

The objective decreases by 48.395344: likelihood improves by 6.093442 and prior penalty by 42.301903. This is a better native training basin than the previous lifted direct release (40240.278465), and a slightly closer configured distance than that endpoint (5.847635 km), but it remains far from the requested accuracy. The original B endpoint remains much closer to the configured reference.

The release passes independent unchanged stationarity at KKT 0.000764262, using 307 complete objective evaluations and 17.981 seconds. SLSQP itself returned stationary; no additional gradient finish was needed. The configured-reference comparison occurred only after the new seal and remains explicitly unconfirmed as ground truth.

Taken together, the crossed profiles and release show two distinct effects: the earlier free fit missed a better available basin, while the improved free solution still trades some geographic movement for reduced regularization cost. This is not proof of a globally optimal native position or a general prior defect. A matched full-frame conditional channel ablation is planned separately; historical C halves without common receiver clocks are not matched controls for this new model.

Evidence: `local/ds22-b-profile-release-v1` and `local/ds22-b-profile-release-comparison-v1`. Both original unlifted and lifted paired controls remain preserved.
