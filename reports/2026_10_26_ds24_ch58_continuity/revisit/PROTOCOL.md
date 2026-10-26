# Natural revisit feasibility, frozen development panel

This single bounded development iteration uses DS24-0010 through DS24-0013,
the first four chronological usable cases, with channels 5–8 and channels 1/4
as controls. Per case/channel, choose the processed RX0 visit nearest the
native-counter scan midpoint (ties earlier), then the next chronological
same-channel/edge visit. Both recorded receivers remain in the denominator.
No target outcome selects a visit. Exactly three earlier processed visits of
the same case/channel/edge/RX are donors, including missing/failing candidates.
These persisted full-window acquisition results are measured donor inputs;
there is no full-scan identity graph, satellite/TLE, position, or GPS input.

Donor candidates must have original rank <=8 and measured margin >=0.025.
Coalesce only aliases within 2 timing samples and 200 Hz, retaining the lowest
original rank. Seed every distinct latest-visit candidate, bounded at eight.
For each seed, the two earlier visits must each contain exactly one distinct
candidate within 64 samples of counter-propagated timing and 5000 Hz of CFO.
Zero matches and multiple matches remain explicit unavailable/ambiguous modes.
These deliberately broad matching gates are assumptions, not identity truth.

Fit ordinary linear CFO and circular timing phase against native-counter
elapsed seconds using only the three donor visits, with the latest donor as
the timing unwrap reference. Forecast to each target. Also retain the latest
donor constant-frequency/constant-timing-rate-zero forecast. For each scalar
fit, the forecast scale is max(floor, donor residual RMS)*sqrt(1+leverage)
plus elapsed time times a fixed evolution allowance. Floors are 50 Hz and
0.5 sample; allowances are 200 Hz/s and 5 samples/s. Three times this scale
is a heuristic uncertainty band, explicitly not a calibrated confidence
interval. No width, threshold, matching, or model sweep is allowed.

Freeze source, metadata-only panel, tests and this protocol before predictions
or IQ outcomes. The predictor receives target counter/rate/edge/RX headers and
earlier donor records only; its tests redact target candidate responses and
verify invariance. Persist predictions independently of evaluation. Full-window
original acquisition candidates are exposed by the preexisting tracking file;
label that exposure in all identity/compatibility claims. They never enter
the forecast or choose a guidance mode.

Open only the 48 fixed target windows through public FastSegmentSource using
the verified source inventory/manifest/index mapper. Exhaust each bounded
reader and check IQ digest, acquisition, target, rate and receiver membership.
Before any corrected/guided scoring, require full paired original-20ms exported
candidate parity, including incomplete/failing nomination membership represented
by the original exported contract. Any parity failure disables that window.
No raw IQ is copied or packaged.

For each eligible earlier-only forecast, score the unchanged conditioned
GLRT64 at its forecast fractional timing and CFO separately on disjoint first
and second 100000-sample halves. Propagate each half's epoch by exact native
counters. Evaluate the constant and linear forecasts at the same point budget;
no target timing search, CFO mode selection, or outcome-dependent replacement.
The scorer profiles its usual residual CFO. Record every proposal and define
the primary as the lowest original donor rank among complete unambiguous
histories. Two halves passing margin 0.025 with tracking CFO agreement <=100 Hz
are independent-support consistency evidence, not established signal identity
or a measured false-confirmation rate. No real signal has external CFO/timing
truth. No localization or production behavior is changed by this experiment.

Each numerical process has a 580-second alarm, BLAS threads fixed to one,
and checkpointed per-window results. Missing, failed, and unattempted cells
remain in all denominators. No new RF or modification of QNAP or frozen prior
studies. Outputs are research sources/tests, seals, predictions, counts, plots,
and limitations; this is not a mandate to tune until a gain appears.
