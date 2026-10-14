# Recorded passing branches do not remove B059's high-band preference

Both source-frozen audits completed,05311.581s and05915.358s, under independent120/135/140-second bounds. **6 original objective calls,6 explicit all-native orbit calls,6 all-native likelihood calls,0 fits.** Each branch uses its own measured native receive time and actual RF with the original frozen correction function. No held/reference data, candidate generation, calibration adjustment or measurement reselection was used.

All selected NLLs replay with exactly zero error; the maximum selected posterior error is4.49e-15, below the unchanged1e-7 source closure gate. The independent per-branch Gaussian density sum also matches the original all-native Hard60 likelihood exactly. Every native query stays inside ephemeris support without clipping; minimum support slack is1.472471s across the six states. The inventories contain5409/6907 passing branch points over1870/2522 selected windows for053/059, matching the preceding source projection audit.

The important result is a **robust, opposed fixed-state preference**. For059, even the most donor-favorable common branch at every high-band window cannot reverse that band's preference for the far incumbent. RX1 favors the donor even under its least favorable branch choices. These results concern the three fixed physical states and B's original folded Gaussian density; they do not prove emitter identities or exclude improvements after model/state reoptimization.

## Common-branch likelihood-ratio bounds

For each window and each recorded passing branch, compute donor NLL minus incumbent NLL on that **same branch**, with its own support-center time. Sum the per-window minima/maxima. Any common single-branch selection from this fixed inventory lies within these bounds. The extremal choices depend on the inspected states and are diagnostics, not a deployable selector, normalized detector-history likelihood, or localization improvement.

| Case / alternative | Original selected NLL gap | Minimum common-branch gap | Maximum common-branch gap |
|---|---:|---:|---:|
| 053 fitted A donor | +214.046095 | −608.387001 | +935.323375 |
| 053 original start3, rejected | +134.377302 | −730.002561 | +823.896243 |
| 059 fitted A donor | +453.406707 | −639.900532 | +1415.157601 |
| 059 original start3 | +675.764562 | −861.047760 | +2146.034909 |

The full-inventory intervals span both signs. Thus this audit does **not** rule out an effect of selected-peak censorship on the overall ranking. It also does not supply a training-only peak policy that achieves the favorable bound: attaining the donor lower bound requires unselected branches at1089/2522 windows in059 and903/1870 in053.

The059 donor decomposition is more restrictive:

| Scored subset | Windows | Selected gap | Minimum bound | Maximum bound |
|---|---:|---:|---:|---:|
| Low band | 1550 | −103.375266 | −904.238219 | +648.634525 |
| High band | 972 | +556.781973 | **+264.337688** | +766.523077 |
| RX0 | 1820 | +1002.111398 | **+63.255397** | +1796.184275 |
| RX1 | 702 | −548.704691 | −703.155929 | **−381.026674** |
| CH6, both receivers | 269 | +289.747555 | **+218.900026** | +337.784572 |
| CH7, both receivers | 226 | +172.341909 | **+78.181230** | +224.909746 |

Every RX0 high-band channel remains adverse to the donor under its own most favorable common-branch bound:

| RX0 subset | Windows | Selected gap | Minimum bound | Maximum bound |
|---|---:|---:|---:|---:|
| CH5 | 192 | +87.479471 | +33.223992 | +152.677446 |
| CH6 | 185 | +277.024807 | +216.934447 | +319.742523 |
| CH7 | 187 | +279.959263 | +187.541331 | +324.367772 |
| CH8 | 146 | +114.272702 | +50.593639 | +144.877550 |

RX1 CH1/2/4/5/7/8 favor the donor even at their maximum common-branch gaps. RX1 CH6 still favors the incumbent, while CH3 spans both signs. This is more specific than a universal receiver bias. The original near/start3 also cannot beat the far state on CH3 or CH6 under any common branch choice, although its high-band aggregate interval spans both signs. Different nearby physical/calibration states therefore retain different channel conflicts.

For053 the donor's high-band interval spans−294.805675 to+304.388209; CH1 and CH2 remain adverse even at minimum gaps+28.643971/+37.380547. The same instrumentation runs without singling out059 or using truth to choose windows.

## Independent state maxima are a different diagnostic

The sums of per-window best-density gains relative to each state's original selected peak are:

| Case | Incumbent gain | Donor gain | Original start3 gain |
|---|---:|---:|---:|
| 053 | 370.847438 | 338.396449 | 377.851164 |
| 059 | 543.353926 | 517.158218 | 524.932808 |

The far state has slightly more potential gain than the donor in both cases. These maxima choose different observations for different states and are **not comparable normalized model likelihoods**. They neither promote an endpoint nor estimate the benefit of a real candidate-set likelihood. The common-branch bounds above avoid that particular comparison error, but remain counterfactual bounds.

## Consequence for the next hypothesis

The earlier revisit audit found only one selected-CFO jump and no native rescues on059 CH7. The present audit goes beyond continuity: even all recorded passing alternatives cannot reverse CH6/7's aggregate donor disadvantage under unchanged B physics. A generic persistence penalty or a simple best-peak replacement is therefore unsupported as a repair of those fixed-state preferences.

The next separately authorized test is zero-fit scoring of the same three complete B states through the existing native-clock likelihood, with exact native-time physical correction transport and each state's deterministic training-modal receiver lift. Compare **within-native** perreceiver/channel gaps, not raw B versus C objective values. This changes the observational likelihood and removes B's extra227kHz equivalences while preserving complete fitted calibration/timing state. Source qualification must separate those effects from a receiver-lift transfer error. The existing DS22 [alias audit](B_NATIVE_ALIAS_AUDIT.md) and [lifted transfer](B_NATIVE_LIFTED_TRANSFER_RESULTS.md) already demonstrate why a lift is required and why it need not repair a wrong location; this is not a newly discovered missing-lift bug in original C. No fit follows from the branch extrema.

Source/protocol`2aaac7d30`;6 component/runner tests and Ruff passed. Runtime `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-b-passing-branch-audit-v1`. Full branch records retain CFO, support endpoints, RF, receiver/channel, rank, margin, GLRT scores and per-state densities/assignments. Terminal SHA256:053`4ea0663adbd71316590bba2b8e5b27e88c612417a55820c5a205e6457c6ca9f5`;059`f00705fefdb285c9526c664641acbe17e5c6c677172e1b1162484546cec43d4c`. Seal SHA256:053`73fec3caae1fdbdbd7e200dd927758d032b0845490a83085f86c33951e1f72b6`;059`aaca2036c18b7d2bdb64746af77e9230a43b35e3b55b6ab16a1833308ac7c7c4`. Original eligibility, selected endpoints, accuracy results and histograms are unchanged.
