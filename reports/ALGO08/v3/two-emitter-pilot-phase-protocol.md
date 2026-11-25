# Phase agreement with two overlapping simulated emitters

Use one 20 ms stereo opportunity per case. Generate CI16 in memory with
the released Qin upper-edge simulation pilot and unchanged installed
20 ms cancellation detector. Both transmitters, when active, occupy the
same sampled RF channel and time window. The station is an arbitrary
local plane with an 18 m baseline and no Gauss coordinates, calibration
or orbital data. Project two fixed far-field directions onto the
baseline. Include a case where their projections coincide. Plant exact
receive epochs and signed carrier frequencies separately for both
emitters and radios. Use fixed, independent carrier phases and seeded
receiver noise. Change relative gains to swap which transmitter is
strongest while retaining both pilots on both radios.

The case table in the runner is the enrollment. Include an all-empty
and a one-positive control, the same transmitter on both radios with
and without a decoy, swapped emitters with exactly coincident and
separated dominant arrivals, a near carrier-alias case, an exact
carrier-alias case, and indistinguishable coincident waveforms. Do not
rerun with other parameters if a detector misses or resolves the
mixture unexpectedly.

Run each mixture and each present emitter in isolation with the same
noise realization, using the installed native cancellation ABI.
Retain every exported factor and select the highest verified margin
with native rank as the tie break. Assign a mixture winner only if
exactly one planted emitter is within 1 kHz in **signed** CFO, its
isolated winner reproduces its signed CFO within 1 kHz, and no gated
factor from another isolated emitter falls within 1 kHz of the mixture
winner. This is counterfactual signed-carrier support in a controlled
fixture. The association uses neither measured epoch nor planted gain
rank. Coincident signed carriers or conflicting aliases remain
ambiguous. Missing detections remain missing.

Use the frozen phase rule verbatim on every pair of gated mixture
winners. At the shared stereo counter, wrap RX2 minus RX1 fractional
epoch by 40,000/3 samples and use absolute difference at most two
samples without fitting a correction. Report pair agreement separately
for supported same-emitter, supported different-emitter and ambiguous
pairs. Count all absent or one-radio pairs. A single signed-supported
different-emitter agreement disproves phase agreement as a sufficient
identity condition. Marginal mixtures and nondetections are part of
the denominator. This constructed fixture gives no field error rates.

The earlier public simulations plant one shared pilot per time/RF;
their stressed predecessor adds QPSK without a competing pilot.
Existing joint pilot experiments run on previously observed mixtures.
This experiment uses no recording or TLE files. Cap nine mixtures and
54 lane calls, including isolated controls, under one nonblocking
idle Gauss lease, one low-priority CPU and a 12-second process cutoff.
The earlier measured wide GLRT of 27.68 CPU seconds for 1,200 stereo
visits prices the native-call ceiling near 0.63 CPU seconds before
synthesis, imports and context setup.
[Prior wide GLRT](../../2026_11_19_receiver_screening/acquisition-frontier/waveform-holdout/README.md) ·
[Frozen phase census](radio-consistency-custody-protocol.md)
