# Joint location with a shared, soft receiver cone factor

Freeze all eighteen consecutive DS7/DS8/DS9 four/eight panels at four equal
RX half-angles: 20,30,40,50 degrees, executed in order c20,c30,c40,c50.
Widths and nominal axes are shared across every track and time in a panel.
Axes are +/-10 degrees from zenith toward west/east; world pointing remains
an assumption. Do not choose a width using reference error or compare raw
training objective values across widths to select a winner. Retain all 72
panel/width outcomes, including failed fits/audits, in the completed study.

Retain one common E/N location and one timing per recording. This is separate
from the receiver-specific timing experiments. Keep the same Student-t4/100Hz
zero-decay track likelihood, offset prior, candidate bank and observation split.
For each candidate/track let theta be its maximum boresight angle over all
TRAINING observations. Add log g to its training score, where
g = .01 + .99*sigmoid((half_angle-theta)/2 degrees). The .01 floor retains
out-of-cone explanations. It is a fixed compatibility factor, not a measured
sidelobe probability, calibrated clutter model, or hard cone constraint.

The factor uses the whole sampled training trajectory at a single fixed RX
cone and the current fitted location/timing. Max-angle ties are piecewise
smooth; finite-difference audits remain mandatory. No track or candidate is
removed solely for cone inconsistency. The horizon rule is unchanged.

Held Doppler prediction conditions on the SAME training geometry factor:
add log g to both the full Doppler joint and training mixture before taking
their log difference. Do not recompute g using held observations. This scores
frequency prediction conditional on training cone compatibility; it does NOT
score held detections/non-detections or enforce a hard cone on held samples.
The soft factor's physical calibration and uncertain world pose are not solved.

Four starts per panel/width: generic E/N (0,0),(3,-3),(-3,3) km with zero
timings, and the one-timing baseline training-selected point. No geography-
selected initialization. Bounds E/N +/-12 km and timings +/-5 s. L-BFGS-B
maxiter140/maxfun200/ftol1e-14/gtol1e-8/maxls30. Select greatest training score
among success/interior/gradient-inf<=.01 starts. No retry or gate relaxation.

At each baseline-derived start, disable the cone and reproduce original
training/held rows and gradient within 1e-7. Test enabled geometry derivatives
and held-data isolation on synthetic candidate banks before execution.
Selected-point audits replay training score within 1e-7 and row sums; check
E/N at .001/.0005 km and timings at .0000625/.00003125 s, all discrepancies
<.002. Timing intervals must avoid .25 s interpolation nodes and both timing
numeric derivatives agree within .002. Failures remain failures.

Evaluate swapped-axis and co-pointed factors at each nominal selected point
without refitting. Report them as conditional controls, not equally optimized
alternatives. Main comparisons report all geographic errors, matched held
Doppler changes, dataset/size medians and sub-km counts versus the no-cone
baseline. Full aggregates require all planned members to pass; missing/failed
members remain visible. All widths are sensitivity arms, not calibrated choices.

One worker, BLAS1/nice19, 4 GiB address-space cap, 180 s process cap and >=5 GiB
available memory. Run one width batch at a time. Existing cached inputs only;
no RF, waveform reads, propagation or provider access. Prior partial-timing
s050/s200 batches remain pending; user-requested cone modeling takes priority.
