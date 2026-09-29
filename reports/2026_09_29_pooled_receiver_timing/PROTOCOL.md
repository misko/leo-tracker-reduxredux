# One common receiver timing difference per consecutive panel

Use all eighteen frozen consecutive DS7/DS8/DS9 four/eight panels. Preserve
zero-decay shared-track-scale Student-t4/100 Hz likelihood, candidate banks,
frequency offsets, record membership and train/held partitions. Fit E/N,
one center timing per recording, and one common RX1-minus-RX0 difference d:
RX0_i = center_i - d/2; RX1_i = center_i + d/2. This tests a stable receiver
correction within each panel; it is not assumed to be physical latency.

Bounds: E/N +/-12 km, centers +/-4 s, d +/-2 s. These rectangular bounds
keep both receiver timings within the existing +/-5 s prediction bank.
All prior selected timings are within +/-2.347 s, so every prior baseline
remains feasible at d=0. The center bound is narrower than the prior +/-5 s;
report this distinction and all boundary failures explicitly.

Four starts per panel: E/N (0,0), (3,-3), (-3,3) km with centers/d zero, and
the prior one-timing training-selected position/timings with d=0. No warm
start from geographic truth or the free receiver-timing result. Keep L-BFGS-B
maxiter140/maxfun200/ftol1e-14/gtol1e-8/maxls30. Qualify success, all variables
at least .001 inside bounds, gradient infinity norm <=.01. Select largest
training score among qualified starts. Retain all failed starts; no retries,
fallbacks, outcome-based exclusions or changes to gates after launch.

At d=0 in each nested start, reproduce baseline scores/held rows and its E/N
and tied timing gradients within 1e-7. Test the parameter transformation and
gradient chain rule with unequal quadratic sensitivities before execution.
For every selected fit, replay training score within 1e-7; check E/N at
0.001/0.0005 km and centers/d at .0000625/.00003125 s. Each finite difference
must agree with the analytic gradient within .002. Both timing step intervals
must avoid any changed receiver timing's .25 s interpolation nodes; their
numerical derivatives must agree within .002. Explicit failure flags survive
even when a process completes. No alternate-step review in this experiment.

After selection, compare all eighteen geographic errors and held predictions
against both the one-timing baseline and separate-per-recording RX timings.
Report dataset/size medians, sub-km counts, every regression, generic-only
initialization diagnostics and matched first-four eight-vs-four held changes.
Keep the known late DS9 failure. Exposed unsurveyed reference; no blind claim.

One scientific worker, BLAS1/nice19, 4 GiB address-space cap, 180 s process
cap, >=5 GiB available memory before each job. Freeze code/input hashes and
retain all process receipts. No RF, waveform, propagation or provider work.
