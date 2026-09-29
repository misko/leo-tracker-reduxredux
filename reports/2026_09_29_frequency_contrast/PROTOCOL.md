# Constant-frequency-offset contrast control

Freeze this protocol and source/input hashes before any geographic fit. Use all
18 early/middle/late consecutive four/eight panels from the published consecutive
baseline, with exactly its records, masks, candidate banks and three generic
starts. Do not substitute panels, tune using reference errors, or retry completed
fits. This is a new likelihood, not numerical equivalence to the baseline.

For each track, subtract its first training observation from every other
observation. The zero-decay shared-scale Student-t4 model becomes a Student-t4
on n-1 contrasts with scale matrix 100^2 (I + 11^T). Its determinant is
100^(2(n-1)) n. This exactly eliminates a constant frequency offset and removes
the old weak absolute-offset penalty. The implementation uses centering as
an algebraic evaluation of this contrast density, including for the full joint
density; it does not fit an offset on held observations. Conditional held log
density is full contrast mixture minus training contrast mixture. The training
anchor belongs to training. Retain the original horizon and full-catalogue
normalizer for this control; retained-bank weights are not calibrated identity
probabilities, and this is not a normalized full-catalogue generative model.
No new cone factor, RX timing split, temporal covariance, spatial prior or
unassociated-track alternative is included.

Before freezing, require the eight independent tests for matrix density and all
anchors, flat-offset integration including normalization, conditional-mixture
normalization, density derivatives, geographic/timing derivatives, frequency
translation invariance, held-data isolation and per-training-anchor held replay.

One shared E/N position and one timing per recording. Starts (0,0), (3,-3),
(-3,3) km, all timings zero. Bounds E/N +/-12 km, timing +/-5 s. L-BFGS-B:
maxiter 140, maxfun 200, ftol 1e-14, gtol 1e-8, maxls 30. Select greatest
training score among successful fits, no parameter within 0.001 of its bound,
gradient infinity norm <=0.01. No use of held scores or reference error in
selection. Preserve all starts, failures and abstentions. Compare training scores
only within this model, never directly with the baseline's different dimension.

Replay selected training score within 1e-7. Independently finite-difference every
parameter at E/N steps 0.001 and 0.0005 km, and timing steps 0.0000625 and
0.00003125 s. Each difference from the implemented derivative must be <0.002;
timing checks must not cross a quarter-second interpolation node, and their two
numerical derivatives must agree within 0.002. Failed audits remain failed; no
alternate fit, relaxed threshold or outcome-dependent replacement. All panels
remain in the planned denominator. Complete dataset/size medians require all
three block audits to pass.

Report per-panel reference error and held score against the original baseline,
all starts, audit details, sub-km counts, and first-four matched held change for
eight versus four. Reference coordinates are the exposed, unsurveyed station
reference; this does not establish blind accuracy, surveyed accuracy or spatial
resolution. Four/eight sets are nested and the sensitivity results are dependent.

One worker, BLAS1/nice19, 4 GiB address-space limit, 180 s per child process,
MemAvailable >=5 GiB before admission. Each fit and held audit runs in its own
process and records command, exit code, resources and hashes. Resource admission
failure stops the launcher; do not silently restart a completed scientific job.
No RF collection, waveform reads, candidate rebuilds or provider fetches.
