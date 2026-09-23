# Frozen staged fixed-cone full-FOV width sweep

Repeat the published staged candidate/orientation/refit analysis at full fields
of view 10, 25, and 30 degrees, corresponding exactly to half-angles 5, 12.5,
and 15 degrees. Use the same five prespecified cells, twelve TRAIN scans,
candidate caches, 20-degree nominal axis separation, 15-degree maximum shared
tilt, one-degree tilt grid, and five-degree yaw/tilt-azimuth grid.

At each cell and width independently: choose the ordinary visible Doppler winner
for every eligible track using randomized training rows and training-only CFO;
freeze those IDs; fit one shared orientation across all twelve scans using those
IDs; then perform one refit among ordinary-visible candidates with capped
training cost below one that remain inside the cone at every training sample.
Do not alternate or jointly optimize candidate IDs and orientation. Evaluate
held rows only after candidate IDs, CFO, and orientation are frozen.

Keep every eligible track in the occupied-second weighted denominator. Assign
unmatched tracks capped squared-RMS cost one at the prespecified 800 Hz scale.
Report baseline and staged training/held all-track loss, supported tracks,
occupied-second support, observation count, span, supported-only held RMS,
changed IDs, orientations, width ranking, and runtime. Verify exact parity of
the 25-degree arm with the published staged result. Do not infer monotonicity of
the refitted objective across widths because each width refits its orientation.

This is a sampled hard-cone diagnostic, not continuous visibility, calibrated
antenna gain, or a production exclusion rule. Use no truth, VAL/TEST,
geographic optimization, new RF, QNAP write, or deployment.
