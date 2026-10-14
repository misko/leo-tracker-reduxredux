# B059's receiver conflict survives complete lifted native scoring

The two source-frozen zero-fit slices completed:05310.603s and05913.289s. **18 objective evaluations,24 extra orbital predictions,18 extra likelihood evaluations,6 singleton row-density reconstructions,0 fits.** The120/135/140-second caps include source checks and preparation. No held/reference observation was read and no geography, clock, timing, c or group parameter was optimized.

All six fixed states receive the same deterministic source-qualified receiver ambiguity representatives: **RX0−1 and RX1+2 times227272.727273Hz**. Native-time physical correction transport closes within1.17e-10Hz. Prediction, visibility, spatial derivative and timing derivative arrays match exactly between the B and native orbital ports. Native posterior reconstruction errors are exactly zero; maximum singleton row-NLL error is7.28e-12. The complete prior penalty is unchanged exactly. Original wrapped-B objective/NLL invariance under the receiver lifts holds within1.46e-11, with maximum posterior delta1.10e-12. No native score or truth selected these integers.

Under the **same native likelihood**, the059 fitted A-derived state still loses to the far incumbent. The low-band preference for the donor and opposite receiver preferences remain. This negative fixed-state test supplies no basis for a new native fit solely to repair a receiver-lift mistake; it does not exclude improvement after a genuinely different nuisance/geographic optimization.

## Native inventory and scope

| Original native inventory | 053 | 059 |
|---|---:|---:|
| Selected windows | 1870 | 2522 |
| Available native ambiguity-cell representatives | 2707 | 3268 |
| Padded ambiguity slots | 5 | 5 |
| Temporal edges | 0 | 0 |
| Sampling circle, Hz | 2500000 | 2500000 |

This is the **existing native model's inventory**, not the full5409/6907 passing points evaluated in the preceding branch audit. The source `joint_association_native.native_branch_inputs` canonicalizes at the sampling circle, labels each point's nearest227272.727273Hz ambiguity cell, and retains highest margin (then rank/ID) within each cell. This policy uses no fitted frequency or reference. Consequently this experiment changes periodic physics and detector-history normalization while retaining the original cell-representative policy; it does not test an all-passing-peak detector-set likelihood. No temporal edge or waveform measurement was added.

Exact layout checks preserve observations and all bank arrays, affine RF/time design, baseline, timing basis, group frame/design/precision, clock nodes/null/design/precision and score. Every native alternative is predicted at its own stored time/RF. Receiver lifting changes only the corresponding affine intercept. Source c, slopes, group contrasts, common clocks, orbital timing and geography remain unchanged.

| Case/state | RX0 confident windows / modal fraction | RX1 confident windows / modal fraction |
|---|---:|---:|
| 053 incumbent | 797 / .836888 | 182 / .791209 |
| 053 fitted A donor | 755 / .841060 | 153 / .647059 |
| 053 original start3, rejected | 710 / .840845 | 199 / .723618 |
| 059 incumbent | 1070 / .857944 | 277 / .711191 |
| 059 fitted A donor | 775 / .825806 | 429 / .836830 |
| 059 original start3 | 806 / .833747 | 339 / .796460 |

Confidence here is original wrapped satellite responsibility>.5. It is not waveform-based satellite identity. The existing source rule's deterministic tie/fallback was independently reproduced and required to match for each state. Earlier DS22 [receiver-lift qualification](B_NATIVE_ALIAS_AUDIT.md) and [lifted transfer](B_NATIVE_LIFTED_TRANSFER_RESULTS.md) remain separate experiments; this identifies no missing-lift bug in original C initialization.

## Within-native fixed-state gaps

All differences below are alternative minus incumbent **within the same native model**, with the same observations, inventory, bank, calibration frame and score.

| Case/alternative | NLL gap | Prior gap | Native objective gap |
|---|---:|---:|---:|
| 053 fitted A donor | +464.450004 | −103.845301 | +360.604703 |
| 053 original start3, rejected | +399.393343 | −1.464451 | +397.928892 |
| 059 fitted A donor | +567.733654 | −129.289331 | +438.444324 |
| 059 original start3 | +893.019695 | −115.393179 | +777.626516 |

| Native NLL gap subset | 053 donor | 059 donor | 059 original start3 |
|---|---:|---:|---:|
| Low band | +366.493978 | −305.432440 | +1286.613733 |
| High band | +97.956025 | +873.166094 | −393.594039 |
| RX0 | +257.477418 | +1504.449208 | +1373.941483 |
| RX1 | +206.972586 | −936.715553 | −480.921789 |

059's robust RX0 high-channel preference remains at the same complete physical states:

| RX0 subset | Windows | Donor native NLL gap | Original-start3 native NLL gap |
|---|---:|---:|---:|
| CH5 | 192 | +45.027320 | −459.933935 |
| CH6 | 185 | +445.283403 | +274.322310 |
| CH7 | 187 | +491.004621 | +214.878823 |
| CH8 | 146 | +167.048798 | −162.848637 |

RX1 retains donor advantages on CH1/2/4/5/7/8, with disadvantages CH3+59.071062 and CH6+28.986766. Thus this is not a uniform receiver penalty. The two nearby states retain different low/high conflicts even with full calibration transport. These cross-model diagnostic patterns do not put B and native raw objectives on a common evidence scale or attribute a change specifically to alias physics rather than detector normalization.

Native posterior signal mass at059 is1205.681 at the incumbent,1101.439 at the donor and1053.861 at original/start3. The donor gains RX1 mass386.903 versus226.492 but loses RX0 mass714.536 versus979.189. Signal mass is inferred support, not verified detections or an accuracy metric. The source's lower-prior nearby states still lose likelihood under this observational model.

## Remaining question

The original selected-state comparison changes geography **and** the jointly learned calibration/timing state. Exact transport excludes accidental loss of that state during this audit, but does not demonstrate that every geography received equally effective nuisance optimization. The next requested review is therefore the provenance of prior059 fixed-geography nuisance-profile controls, before prescribing any duplicate experiment. If none matches, a common-incumbent-nuisance profile at the three training-selected geographies would discriminate coupled initialization from fixed-state likelihood preference. No additional fit is launched or justified by this report alone. Generic temporal weighting, branch extrema and a missing native lift do not currently supply a demonstrated repair.

Source/protocol`1719b1802`;5 component/runner tests and Ruff passed, including actual B/native-clock models with nonzero receiver lifts, source-modal oracle, complete native correction, all four orbit outputs, row/posterior closure and clock-prior mutation rejection. Runtime `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-b-native-state-audit-v1`. Terminal SHA256:053`4e35d08deb9b375bd658bfca7a6e67cc6ccb80cf480952ce705107f0a6db069f`;059`21ebedde53f95ff8730d029f474177c600a193703e54daf0c9dfeebaf0169a97`. Seal SHA256:053`6bcccff4aee1e8c0beef2c1da1a6829ce588ecbac80b33269ee0b04dc6da85bf`;059`fd8e8a4adcc9508494481b8658b8bc54b716962d0504b7f90c198e60c822337c`. Original eligibility, endpoints, histogram rows and accuracy results remain unchanged.
