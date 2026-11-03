# Cross-band receiver drift predicts held differences, with small median gain

The frozen eight-scan measurement screen passes its declared gate: seven scans
have positive source-averaged gain, and both mean and median scan gain are
positive. This is a conditional receiver-difference prediction result, not a
positioning improvement or a hardware calibration.

| Original scan index | Reduction in held absolute difference error, native Hz |
|---|---:|
|0|0.1181|
|4|4.2405|
|8|0.0737|
|12|10.8491|
|16|6.4546|
|20|-1.7667|
|24|0.4282|
|28|0.0294|

Mean scan gain is 2.5534 Hz; median is 0.2731 Hz. Of 130 evaluated track pairs,
79 improve. All 130 have enough donor support and a qualified fitted slope.
There are 2,600 held pairs; 2,189 receive the drift prediction and 411 retain
the constant prediction outside the donor-center time interval. Slopes range
from -5.684 to +3.888 native Hz/s, with median +0.201 Hz/s.

Each target's conditional NORAD is excluded across all donor RF bands. Each
other NORAD contributes one median training time/offset center; a Theil-Sen
slope fits these centers. The target uses its own training median to anchor the
intercept. The control uses its own constant training offset. Only original
held/held pairs evaluate prediction; mixed-mask and non-simultaneous rows are
excluded. No target held frequency enters calibration, donor selection or
correction application. The identities themselves remain conditional on the
original training-position solution.

This differs from the earlier DS7–9 pair-specific, same-RF drift experiment:
donors here exclude the target NORAD across RF and provide a shared native-Hz
drift hypothesis. Cross-band sharing is a tested model assumption, not a
verified description of SDR/LNB clock topology. Common drift is still
unidentifiable from receiver differences, and allocating a correction to RX0,
RX1 or both can produce different positions.

The median gain is small and does not justify immediate geographic promotion.
The next check should retain this exact model on the remaining original scans
before changing measurements for position fitting. Any subsequent correction
must keep all receiver-allocation assumptions visible, use the same causal
orbits and preserve unsupported fallbacks. Earlier negative geographic drift
results remain evidence against expecting a position gain from pair agreement
alone.

Two component tests pass for injected wrapped drift, support and slope gates,
and exact fallback outside donor time coverage. The single-thread execution
completed in 0.66 seconds under a 90-second cap with exit0. Source digests and
an independently implemented held-error aggregation verify successfully.
The verifier does not independently reconstruct all measurement predictions.
No IQ, RF collection, new orbit, geographic reference or position fit was used.
