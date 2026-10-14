# Recovered A035/A053: low-to-final component audit

The recovered training-selected winners improve both band likelihoods relative to their own low-function final seeds. Restoring any one saved low component worsens both bands, as do the declared paired restorations. These are coupled fitted modes; this audit identifies no isolated clock, timing or common/RF defect in the recovered winners. It makes no new optimizer, reference or held-data calls.

Each case retains one exact candidate bank, full observation frame, priors and winner-specific learned high contrast. The 035 family is the retained-twelve fixed55 locked-high winner BEFORE 5. The 053 family is the same fixed59 BEFORE 5 family after the accepted 50 km continuation. Low functions are represented by their actual full-frame final seed, preserving the original clock and calibration gauge. Clamps use that projection rather than copying coefficients from a different observation frame. Absolute timings are restored as a complete vector on the same ordered bank. Every state is an unfitted diagnostic and remains ineligible for selection.

| Case / state | Full training objective | Low NLL | High NLL |
|---|---:|---:|---:|
| 035 own-low function final seed | 35873.485673 | 20682.912157 | 14835.994832 |
| 035 selected final | 35642.819252 | 20664.912028 | 14603.986411 |
| 035 restore low geography | 37851.481182 | 22050.769075 | 15426.791295 |
| 035 restore low timings | 38961.184786 | 22439.255756 | 16144.358599 |
| 035 restore low common/RF | 36172.704443 | 20941.710599 | 14857.073031 |
| 035 restore low clock | 36009.166428 | 20857.773877 | 14800.463486 |
| 035 restore low common/RF and clock | 36426.781962 | 21062.033256 | 15013.819640 |
| 035 restore low geography and timings | 36533.472007 | 21053.299944 | 15102.601632 |
| 053 own-low function final seed | 23743.287792 | 15630.682272 | 7784.499670 |
| 053 original 25 km joint endpoint | 23680.725142 | 15658.116252 | 7682.974702 |
| 053 selected 50 km endpoint | 23498.663735 | 15606.688314 | 7606.432784 |
| 053 restore low geography | 27466.785905 | 18565.438636 | 8615.804632 |
| 053 restore low timings | 27607.453407 | 18631.127230 | 8695.219276 |
| 053 restore low common/RF | 24043.947944 | 16057.112182 | 7701.293124 |
| 053 restore low clock | 24253.101254 | 16039.435232 | 7881.124436 |
| 053 restore low common/RF and clock | 24503.447040 | 16368.320663 | 7802.584791 |
| 053 restore low geography and timings | 24760.825022 | 16463.151874 | 8016.566248 |

Complete restoration reproduces the own-low function seed exactly. The 035 joint and selected endpoint are the same checkpoint. Those duplicate states are deliberately replayed in the declared twenty-evaluation inventory; the JSON retains every state, native band score and source binding. Every original-joint and selected full objective reproduces its saved receipt within 1e-6, and each own-low seed's low NLL reproduces its saved low-stage NLL within 1e-6.

From its low seed, 035 moves 0.732549 km in the regional plane and changes absolute satellite timings by 0.486045 seconds RMS. The common/RF correction changes by 100.536485 Hz RMS over the actual full observation rows, and the clock contribution by 75.373187 Hz RMS. The selected endpoint has lower NLL in both bands. Restoring only geography or timing incurs much larger loss than restoring the whole low state, demonstrating that individual changes compensate one another. Their score differences must not be added or interpreted as independent causal contributions.

The 053 expanded endpoint moves 7.057869 km from its low seed, changes absolute timings by 1.052514 seconds RMS, and changes common/RF and clock contributions by 140.611942 and 142.068077 Hz RMS. Its original 25 km joint stage modestly worsened low NLL by 27.433979 while improving high NLL; the 50 km continuation recovers that low-band loss and improves both bands relative to the low seed. This differs from the destructive original high-stage handoff documented earlier. The recovered 3.476 km endpoint is geographically interior to its 50 km disk; the recovered 035 6.290 km endpoint is also interior. This diagnostic does not justify additional radius expansion or identify an isolated component to replace.

Source `tools/model_a_selected_component_audit.py` is committed as 7bcb12e38. Three component tests pass and Ruff passes, including genuine native orbit/clock/likelihood fixtures, block isolation without input aliasing, full twenty-state durable serialization and duplicate-attempt rejection. The actual source freeze takes 4.538 seconds. The complete audit takes 5.225 seconds and makes twenty full objective evaluations, twenty explicit orbit predictions and forty band likelihood evaluations, plus objective-internal predictions. It makes zero optimizer, reference or held-data calls. Bounds are 120 seconds internal, external TERM at 135 and KILL at 140. The exclusive launch, complete termination and exact immutable source/ancestor inventories remain bound.

Authority: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-a-selected-component-audit-035053-v1`. The adjacent JSON preserves the full audit and source hashes. Better in-sample scores and these coupled counterfactuals do not prove whether the residual position error comes from model bias, association ambiguity or another calibration basin. A future fixed-geography full-nuisance profile/release control must use explicitly identified training-selected geography donors and a single shared own A parameterization/domain. A has no independent high-geography estimate: its high stage inherits low geography. No new fit is authorized or launched by this report.
