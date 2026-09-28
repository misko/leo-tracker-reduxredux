# Frozen-model temporal transfer

Apply the completed six-fold calibration cross-validation models to each omitted recording's later held-frequency period. This is a separate no-refit diagnostic. It retains recording membership, model parameters, reference and feature transformation so that early and later predictive scores can be compared within a recording. It does not modify the preceding cross-validation result or use its new outcomes for selection.

## Frozen inputs and transform

Bind the original pilot dataset and `2026_09_28_rx_within_geometry_cv/results.json` by digest. Require the cross-validation result to be complete, its dataset hash to match, and six distinct omitted calibration recordings. Each fold's coefficients, occupancy, persistence, sigma=500Hz, reference distribution and feature scaler remain exactly frozen. Only the fold's omitted recording is scored. No original evaluation or confirmation recordings enter.

The absolute family uses its saved standardization. The within family computes the lane × nominee × receiver mean of standardized geometry columns3:8 over reception forecasts only, then subtracts that same offset from both reception and held-frequency forecasts. This mean includes all nominated forecasts, including invisible ones, and no observed outcomes. Do not center the later block separately. D columns0:3 stay unchanged.

## Scoring and controls

Initialize each exact lane at its frozen conditional nomination prior and fitted stationary presence. Filter reception observations, then carry the posterior through the actual gap into held-frequency observations. Score each observation before consuming it. Export scores, reference densities, window IDs, timestamps, role counts and posterior summaries for both roles. Reception predictive scores must reproduce the earlier cross-validation result within1e-8 total nats. D fits/scores must agree between families.

For every family score D/E/S/T and their fixed quarter-alias-period frequency-shift controls. For T additionally swap differential receiver geometry and reverse the geometry trajectory within each role, using the existing frozen definitions. Controls reuse all fitted parameters and process their own reception history; they are never refitted. Within-family controls subtract the controlled reception feature mean and carry it unchanged into the held block. No geometry-control result may be used to choose a sign or feature after scoring.

Report equal-six-record means separately for reception and held-frequency observations: every arm versus reference, E−D, S−D, S−E, T−S, T−swap, T−reverse and each arm versus frequency shift. Report per-record signs and paired held-minus-reception differences. Keep their original denominators. A temporal difference is descriptive: forecast age, role construction, detector changes and target intermittency remain alternative explanations. These observations do not independently establish a satellite identity or physical travel direction.

## Verification and execution

Test reception-only centering, immutable inputs, carried filtering, score-before-update, exact null, reference/full additivity and reception replay. Independently audit all six fold memberships, raw reference densities, role/window denominators, reception replay, posterior normalization, control scores and aggregate arithmetic. No model fitting or optimizer may be invoked. Freeze source/tests/protocol/input hashes before running; one numerical thread, nice19,4GiB and at most120seconds. No RF, raw IQ or QNAP writes.
