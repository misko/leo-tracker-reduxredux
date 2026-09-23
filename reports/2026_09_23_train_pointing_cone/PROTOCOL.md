# Frozen TRAIN pointing-cone pilot

Use the six locations frozen in `locations.json`: the two retained 50 km Reno
beam cells and final selected point for each TRAIN group's first six scans. Use
training rows only and choose fixed winning candidate identities independently
at each frozen location with the published Doppler scorer. Run no geographic
optimization and use no held rows or reference coordinates.

Recover exact receiver IDs from the separately hash-bound metadata checkpoints.
For every selected track, use its duration weight and satellite line-of-sight at
the track midpoint. Profile one common mount orientation across all six scans in
a view, never per scan or track. Evaluate both RX0/RX1-to-slot mappings, nominal
20-degree relative mount axes, full 0–355 degree yaw and tilt azimuth in
five-degree increments,
and maximum common tilt scenarios 0, 15, and 30 degrees using a one-degree grid.
Use receiver-local east/north/up coordinates. Define fixture body axes as
`(-sin(10°), 0, cos(10°))` and `(+sin(10°), 0, cos(10°))`, exactly 20° apart.
Apply a common body tilt from up with arbitrary horizontal tilt azimuth, bounded
by the scenario, then a mount yaw about the tilted body-up axis; document the
rotation order in source and verify the transformed axes remain 20° apart.
For each mapping/scenario report the minimum weighted 50%, 80%, and 95% angular
quantiles across orientation. At each selected optimum, recompute angles at
track endpoints and report quantiles as a midpoint-approximation sensitivity,
using the same candidate, location, mapping, and orientation without
re-selection. Define a weighted quantile as the smallest sorted angle whose
cumulative duration weight reaches the requested fraction of total weight.

Bind the frozen locations, selected candidate identities, training masks,
duration weights, cache/receipt contents, receiver metadata checkpoints, and
causal TLE-derived state inputs in the inference artifact.

These cone widths are geometric support requirements, not calibrated RF beam
widths or gain likelihoods. Do not choose a location or scenario by geometry or
truth. Preserve both mappings and every scenario. RF boresight is unmeasured,
mapping provisional, tilt scenarios assumptions, and the reported 79-degree
axis is not used as calibration.
