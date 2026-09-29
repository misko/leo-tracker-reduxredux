# Receiver cones with normalized transfer to an unassociated trend

Freeze all four arms before geographic fits: equal RX half-angles 20, 30, 40,
50 degrees, a fixed 2-degree sigmoid edge and no floor. Half-angle is measured
from a receiver axis, not the full opening or the separate 20-degree axis
separation. Assumed axes are 10 degrees west/east of zenith; world pose and
receiver cable mapping remain provisional. No width is selected using location
or held outcomes. Run arms in order c20, c30, c40, c50; completed-arm reports
are checkpoints, never a claim that later frozen arms have been evaluated.

Keep the 18 consecutive early/middle/late four/eight panels, original candidates,
masks and shared E/N plus one timing per scan. Every scan set has one fixed
axis pair and cone width. Each track candidate retains one trajectory. For each
candidate use the maximum training-observation boresight angle. Let g be the
sigmoid compatibility, K the number of retained training-horizon-visible
candidates, and q=0.20. Satellite k has prior mass (1-q) g_k/K; the unassociated
trend has q+(1-q)(1-mean(g)). Both candidate and background weight derivatives
must be included. Require K>0, as in the control; empty visible banks explicitly
abstain. Do not silently recover omitted catalogue hypotheses.

Reuse the completed unassociated-trend q020 model: signal Student-t4 frequency
contrasts, noise scale 100 Hz, trend slope scale 2000 Hz/s, flat constant-offset
elimination. These are uncalibrated prototype priors. The mixture is normalized
conditional on the data-selected retained visible bank, not a full-catalogue
detection model or calibrated satellite identity posterior.

Full/training density ratios keep the same training-derived geometry weights.
Held angles must not alter training or predictive weights. Separately report
signal posterior mass inside the nominal cone throughout training and held,
including conditional held support among training-supported candidates. This
is a descriptive support check, not a hard held cone, reception/non-reception
likelihood, paired satellite identity or proven travel direction. The soft edge
does not enforce literal hard rejection. Swapped and co-pointed axes are scored
at the nominal selected point without refitting; label them conditional controls.

Nine synthetic tests must pass before freezing: mass conservation/invisible
candidates, no-cone replay including q=0/1, zero-cone zero force, common-factor
attenuation, conditional held normalization, all-width/all-parameter derivatives,
the necessary background-weight derivative, held-data isolation, and RX-swap/
co-pointed symmetry. Use the published cone-frame helper and immutable published
contrast/trend model code as explicit research dependencies.

Use three generic E/N starts (0,0), (3,-3), (-3,3) km with zero timings, plus
the prior q020 training-selected position and timings as a fourth start named
no_cone. It is not a reference-informed start. Report the generic-only best
alongside the four-start selection to expose initialization effects. Bounds:
E/N +/-12 km, timings +/-5 s. L-BFGS-B maxiter140, maxfun200, ftol1e-14,
gtol1e-8, maxls30. Select highest training score among successful fits with
gradient infinity norm <=0.01 and distance from all bounds >=0.001. Preserve
every failure and abstention. Never retry completed fits or substitute a
different fit after a selected audit fails.

Replay selected training scores within 1e-7. Check every coordinate at two
steps: E/N 0.001/0.0005 km, timing 62.5/31.25 microseconds. Every derivative
discrepancy must be <0.002; timing checks must avoid quarter-second interpolation
nodes and agree with each other within 0.002. Prediction stencils must retain
the visible set. Also replay the no-cone implementation against the old q020
model at each selected point, requiring scores, gradients, held predictions
and signal responsibilities to agree within 1e-7. Do not relax audit gates.

All three block audits are required for a complete dataset/size median. Report
all 18 planned rows per arm, location and held change versus published q020,
first-four matched eight-minus-four held predictions, signal responsibility,
geometry support and controls. Counts across nested windows and width arms
are dependent. Exposed unsurveyed reference error does not establish blind
accuracy, identifiability or calibrated resolution.

One worker, BLAS1/nice19, 4 GiB address-space cap, 180 s per child, at least
5 GiB MemAvailable before admission. A memory admission failure stops the
launcher without silently retrying scientific jobs. Seal all sources/inputs
before launch and verify the complete seal when reporting. Before and after
each child, verify every execution source and that child's input artifacts,
manifest and donor evidence. Avoid repeatedly hashing unrelated panels' banks:
the preceding study spent 826.85 s in children while additionally rehashing
all 72 recordings for each child. Record explicit per-child dependencies and
the full-seal hash. No RF collection, raw waveforms, propagation or provider
fetches are permitted in this experiment.
