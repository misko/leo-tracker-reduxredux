# Native profile-then-release control

Releasing the accepted native-C profile at B's training-selected geography reaches a new lower stationary objective, but again moves away from B's configured-reference location. Most of the observed objective decrease is a reduction in prior penalty, with a smaller likelihood improvement. This accounting alone does not establish a causal prior bias.

Source `8c83de949` binds the complete crossed-state diagnostic, including its failed profiles, and starts exactly from the accepted B-geography profile. It performs one new free fit in the original B-winning disk: fitted c, 20 seconds, at most 600 actual objective evaluations across the original solver and optional strict gradient finish. No failed crossed fit was retried, no seed was selected by reference distance, and no held observations were read.

| State | Objective | NLL | Prior penalty | Configured-reference distance, km |
|---|---:|---:|---:|---:|
| Accepted fixed B-geography profile | 40153.718553 | 39727.186565 | 426.531988 | 0.785018 |
| Free release from that profile | 40105.323209 | 39721.093124 | 384.230085 | 5.582157 |

The objective decreases by 48.395344: likelihood improves by 6.093442 and prior penalty by 42.301903. This is a better native training basin than the previous lifted direct release (40240.278465), and a slightly closer configured distance than that endpoint (5.847635 km), but it remains far from the requested accuracy. The original B endpoint remains much closer to the configured reference.

The release passes independent unchanged stationarity at KKT 0.000764262, using 307 complete objective evaluations and 17.981 seconds. SLSQP itself returned stationary; no additional gradient finish was needed. The configured-reference comparison occurred only after the new seal and remains explicitly unconfirmed as ground truth.

Taken together, the crossed profiles and release show two distinct effects: the earlier free fit missed a better available basin, while the improved free solution still trades some geographic movement for reduced regularization cost. This is not proof of a globally optimal native position or a general prior defect. A matched full-frame conditional channel ablation is planned separately; historical C halves without common receiver clocks are not matched controls for this new model.

Evidence: `local/ds22-b-profile-release-v1` and `local/ds22-b-profile-release-comparison-v1`. Both original unlifted and lifted paired controls remain preserved.

The separately frozen zero-fit decomposition (`8bb2994b6`, two objective evaluations, no fits) gives the following endpoint differences, released minus fixed:

| Component | Difference |
|---|---:|
| CH1–4 NLL, 1811 windows | +13.795432 |
| CH5–8 NLL, 1418 windows | −19.888874 |
| Common-clock prior | −43.669769 |
| Relative satellite-timing prior | +1.470067 |
| Common timing prior | −0.102590 |
| Group-contrast prior | +0.000389 |

The lower-band likelihood worsens while the upper band improves; common-clock regularization supplies the largest objective reduction. A matched prior-sensitivity control would be needed to attribute geographic bias to that prior. The original likelihood uses 2.5 MHz sampling, 46 satellite candidates and five native slots, with one/two/three available branches on 2022/1082/125 windows respectively. No waveform candidates have measured evidence. These metadata describe the native association model, not a normalization-error finding. Detailed evidence: `local/ds22-b-release-scores-v1`.
