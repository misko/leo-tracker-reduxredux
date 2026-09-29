# Fixed-point, scan-consistent receiver cone support audit

First audit cone support before introducing a discontinuous location objective.
Use all eighteen fixed consecutive four/eight DS7/DS8/DS9 panels and their
one-timing model's training-selected position/timings. Do not use reference
coordinates to choose a position, cone, candidate or orientation. No refit.

Interpret requested 20/30/40/50 degrees as HALF-ANGLES from the pointing axis,
explicitly provisional pending operator clarification. Evaluate all sixteen
RX0/RX1 width pairs, not just four equal-width cases. Nominal ENU boresights
are (-sin10,0,cos10) and (+sin10,0,cos10), separated by 20 degrees. These are
assumed sky axes, not surveyed axes. Include swapped RX axes and a co-pointed
zenith control; do not select one from evaluation outcomes.

One position and one pair of fixed axes/widths apply to every track/time in a
panel, hence throughout each scan. For each bank candidate retain the SAME
trajectory across all a track's training observations; it supports a cone only
if every training LOS lies inside it. Compute LOS from cached candidate ECEF
positions using the baseline's linear timing interpolation and WGS84 surface
receiver position. Do not alter timing to make a candidate fit a cone.

Retain every track. Report geometric candidate support count, minimum required
half-angle among bank candidates, and retained baseline training-posterior
mass for each width/orientation. Distinguish zero stored posterior mass from
zero geometric candidate support. A zero float weight may reflect underflow.
For held observations report all-inside mass conditional on training-cone
support, using only the frozen baseline training weights. Never use held
points to decide training support or refit candidate weights.

Aggregate all sixteen shared width pairs by receiver, recording and panel.
Report unsupported tracks and scans explicitly. A panel is geometrically
supported here only if every track has at least one supporting BANK candidate;
this does not establish correct identity, pairing across receivers, calibrated
beam response, continuous-time visibility between samples, or a new position.
No paired-identity constraint is claimed without verified cross-RX matches.

Test interpolation, coordinate-frame rotation, nominal separation, RX swap,
whole-track support (not just one passing observation), and held isolation.
Verify exact track identities/counts and baseline held-row bindings. Run one
bounded worker at a time after the current timing fitting batch is terminal:
BLAS1/nice19, 90 s, 4 GiB address space, >=5 GiB available memory. No RF, raw
waveform reads, propagation or provider fetch. Preserve all failures and hashes.
