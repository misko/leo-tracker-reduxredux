# A035/A053 complete-incumbent cross-view decomposition

The A053 comparison still has a half-view search shortfall: the full-model endpoint, evaluated under the CH1–4 objective, scores **12921.926725**, already below the accepted CH1–4 endpoint's **13086.953686**. The latter's 0.190263 km error is a valid incumbent result but not evidence that the low-view search reached its best basin. The full state is nonstationary under the low-view mask and cannot simply replace it as an accepted solution. The fresh low-view call failed strict KKT; its lower objective remains evidence motivating a bounded numerical repair.

This diagnostic replayed each current full/low/high complete state through all three observation masks, using the exact shared bank, frame, learned offsets, detection-probability prior and own model. It performed 18 objective evaluations and zero fits in 7.100 seconds. Both cases were fixed before evaluation; no reference coordinates were accessed. Full NLL equals the sum of the two half NLLs, while the joint objective includes the prior once. Objective/prior and physical/nuisance gradient partitions close within 8.44e-12. Two tests and Ruff pass.

| Case / complete endpoint | Low NLL | High NLL | Shared prior | Full objective |
| --- | ---: | ---: | ---: | ---: |
| A035 full | 16803.660968 | 11767.944415 | 311.068719 | 28882.674102 |
| A035 low | 16675.368715 | 12255.925186 | 268.382069 | 29199.675970 |
| A035 high | 18443.889751 | 11538.395688 | 184.266310 | 30166.551749 |
| A053 full | 12640.214630 | 6392.843459 | 281.712095 | 19314.770184 |
| A053 low | 12927.917864 | 6363.925220 | 159.035822 | 19450.878907 |
| A053 high | 15122.702442 | 5966.148355 | 176.151379 | 21265.002176 |

For A053, moving from the accepted low complete state to the full complete state improves low NLL by 287.703234, worsens high NLL by 28.918238, and increases the prior by 122.676273: a net full-objective improvement of 136.108722. Thus this particular complete-state comparison does not support the explanation that upper-band fit improvement alone pulls the result away from the low solution. Calibration, timing and satellite weights also change between these states; this is not a fixed-geography nuisance profile or causal hardware attribution.

At the full A053 endpoint, low and high geographic gradients are approximately (-69.469, 51.922) and (69.469, -51.922) NLL/km. They cancel at the joint stationary point. A035 likewise has opposing gradients (-8.391, 300.762) and (8.391, -300.762). This measures a local conditional compromise, not by itself an error in either band or a proposed choice of band weights. No geographic prior contributes to these two coordinates.

Next bounded control: retain the accepted old A053 low incumbent, and test both the fresh failed low endpoint and the current full complete endpoint under the same low objective/domain. Compare endpoint SLSQP repeat and the existing positive-tangent Newton control, preserving all failures. Only training-selected accepted states may update the low comparison; accuracy must be joined after all outcomes seal. No truth-based selection or weighting is permitted.

Source: `2be5a43c4`; evidence: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-a-cross-view-decomposition-v1`. The parent is the exact old/fresh half-incumbent replay. All source bindings and the complete result are sealed; no source models or golden fixtures changed.
