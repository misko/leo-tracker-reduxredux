# Updated B059 state changes the receiver/channel diagnosis

The new accepted donor release from common-nuisance profiling has a **different likelihood conflict** from the earlier donor endpoint. The old strong RX0-high versus RX1 opposition is not a current-state explanation. At the updated state, both receivers favor the far incumbent in aggregate, and the low band—especially CH3—drives the remaining loss.

The source-frozen audit completed in13.087s:2 original objective replays,2 extra orbital predictions,2 exact per-window density decompositions,0 fits, whole120/135/140 bounds. No held, locked or reference observations were read. Both prescribed states are the accepted free releases of the sealed common-nuisance v2 experiment; they were not chosen by error. The unchanged B model, full training observations, candidate bank, calibration frame, priors and fitted c replay exactly. Previous reference distances1.077617km and333.217856km are context from the separately completed postseal evaluator, not inputs to this audit.

## Remaining likelihood and prior gap

Updated donor minus incumbent NLL is310.947606, comprising30.214474 detection/visibility normalization and280.733131 residual-mixture density. Prior penalty is193.699925 lower, leaving the known117.247680 objective loss. Thus normalization alone remains a minor component and the new state still loses mainly likelihood.

| Scored subset | Windows | Updated NLL gap | Earlier donor NLL gap |
|---|---:|---:|---:|
| Low band | 1550 | +282.249292 | −103.375266 |
| High band | 972 | +28.698314 | +556.781973 |
| RX0 | 1820 | +265.983530 | +1002.111398 |
| RX1 | 702 | +44.964076 | −548.704691 |

The earlier branch and native-score bounds remain valid **only at their earlier complete states**. They cannot establish that the updated state has unavoidable RX0-high preference. Common-nuisance optimization changed the channel assignments/calibration jointly, not merely the position error.

| Channel | Updated NLL gap | RX0 contribution | RX1 contribution |
|---|---:|---:|---:|
| CH1 | −234.147295 | −92.746294 | −141.401000 |
| CH2 | +144.651961 | +172.803828 | −28.151867 |
| CH3 | +461.756026 | +345.011121 | +116.744905 |
| CH4 | −90.011401 | −7.981695 | −82.029706 |
| CH5 | −130.673042 | −216.710519 | +86.037477 |
| CH6 | +167.520016 | +147.961723 | +19.558292 |
| CH7 | +27.068071 | +63.231125 | −36.163054 |
| CH8 | −35.216730 | −145.585760 | +110.369030 |

Loss is still distributed rather than isolated to a few windows: positive donor losses total1996.774672, offset by1685.827067 favorable contributions. The top10 positive windows contribute2.192% of positive mass;80% requires449 windows. Deleting a difficult channel/window based on these retrospective score or location effects would be an oracle intervention, not a model repair.

Assignments differ substantially across the full states: satellite/clutter TV averages.643988 low/.735920 high, with1033/1550 and740/972 MAP changes. These compare different geographies and calibration/timing states and do not identify wrong satellites. Updated donor signal mass is1197.433426 versus incumbent1313.123445; inferred signal count is not verified detections. The updated donor's posterior-weighted RMS is lower in both bands (low120.446 versus121.961Hz; high111.756 versus121.675Hz), yet likelihood is worse. Conditional residual RMS therefore cannot stand in for the full observation density or accuracy.

| Prior component | Incumbent | Updated donor |
|---|---:|---:|
| Common timing | .004103 | .011868 |
| Relative satellite timing | 528.180198 | 363.568301 |
| Common receiver clocks | 74.854147 | 45.838257 |
| Receiver band groups | .376347 | .296444 |

## Conditional residual revisits are descriptive

At exact same RX/channel/RF adjacent times with gaps≤1s, matching non-clutter MAP and signal mass≥.9, residual means can remain correlated. Examples:

| Lane | Incumbent eligible pairs / lag1 Pearson | Updated donor pairs / Pearson |
|---|---:|---:|
| RX0 CH3 | 87 / .536391 | 37 / .857433 |
| RX0 CH6 | 71 / .784456 | 39 / .554204 |
| RX0 CH7 | 76 / .215169 | 67 / .659189 |
| RX1 CH3 | 22 / .412060 | 6 / .308342 |

Some lanes lack5 eligible pairs; their correlation is explicitly undefined. Matching MAP and large signal mass do not verify the same emitter. These are fitted mixture-conditional means with state-dependent truncation/assignment and a fitted common clock; correlations cannot estimate independent noise variance, a physical persistence tau or effective sample size. The earlier039 temporal-refresh experiment was negative and assumed unsupported same-emitter persistence. No temporal weight or sigma is fitted from these conditional residuals.

The requested next descriptive step is a source-bound block contribution audit using **only these existing training observations**, retaining actual times/counts and each channel's positive/negative contributions. Original held and locked partitions remain untouched. Any later predictive-calibration proposal must prespecify blocked CV within training, fit only fold-training observations and disclose leakage from the shared full-training discovery/initializers. No new model, parameter, seed search or fit follows from this report alone.

Source/protocol`4628352bf`;4 component/runner tests and Ruff passed, including actual exact two-state decomposition, receiver/channel additive closure, gap/MAP/signal-mass conditions, insufficient-pair handling, source seals and exclusive launch. Runtime `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-b-profiled-window-audit-059-v1`. Terminal SHA256`e52ac4f506a7d95764b25ad28b57e72a57af33d7356595ca6df45998a77c7588`; seal`ff80c00e67b796ed69dfaad0f483c242a00968cb3cbc9972e663bb9d832c456e`. Every window's NLL components, conditional residuals, visibility, clock correction, signal/clutter mass and MAP remain reviewable. Baseline endpoint selection and histograms are unchanged.
