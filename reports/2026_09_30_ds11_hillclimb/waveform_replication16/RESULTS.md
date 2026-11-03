# Scan-16 waveform replication: complete measurements, position gate fails

All124 frozen training observations were extracted and measured successfully.
The public read-only reader verified sampled IQ payloads. One extraction
process completed in24.11seconds and one measurement process in24.87seconds;
both exited0. All rows provide eight frames and eight pilot carriers. No rows
were dropped, replaced or retried, and all81 target localization-held rows
remain untouched. The selected conditional source is NORAD67103.

| Arm | Improved held-symbol predictions | Mean NMSE gain | Median NMSE gain | Search-bound hits |
|---|---:|---:|---:|---:|
|Short, symbols2–65|27/124|-0.007002|-0.003124|2|
|Long, symbols22–221|84/124|+0.001495|+0.000232|0|

Gain is cached-minus-corrected NMSE, averaged over the eight frames. The long
arm improves mean and median prediction on each of the three tracks; the short
arm worsens both on each track. These correlated waveform outcomes are not
independent trials or geographic improvements. Neither held symbols nor the
roof reference select measurements, sources or arms.

Both short-arm search-bound hits are+1500Hz native residual at visit1308, one
on each receiver. Their cached held-symbol NMSE values are1.00424 and1.00273;
long-arm NMSE values are1.00450 and1.00443. The long corrections there are
-765.37Hz and-186.36Hz canonical. Several other large long corrections also
have prediction NMSE near1. This suggests weak predictive pilot evidence in
some excerpts; NMSE alone does not prove absence of a signal or wrong identity.

The frozen position protocol requires both arms to be complete and boundary-
free. Its preparation therefore rejects the measurements before producing a
fit plan. **No position fits or geographic evaluations ran.** The outcome is
unavailable, not a geographic loss or successful replication. The clean long
arm does not override the predeclared two-arm gate. No wider search, filtering,
replacement, or control removal is performed within this experiment.

Evidence: [measurement summary](measurement_summary.json), process receipts
in `attempts/`, and the [position gate outcome](../waveform_position_replication16/gate_outcome.json).
Seven preparation/runner tests and two summary tests pass. The timing-aware
position runner and its reused interpolation pass15 tests with pytest importlib
mode; the first combined invocation encountered a duplicate test-module name
during collection, before any test ran. No source was changed to bypass it.

Manifest SHA256:
`7528b06a5dcf63e7479df71ba80c4d3defafdc29ca4d743fd5e2449e2358ac0e`.
The50 source bindings,124 identities, saved excerpt digests, and correction
conventions are verified by the summary. No production component, golden
fixture, new RF collection or offline orbit data is involved.

A follow-up should measure pilot-frequency reliability from its fitting
symbols before deciding how to combine pilot and cached GLRT frequencies.
Simply widening a search on weak evidence could yield a finite but unreliable
frequency. Any revised arm policy or uncertainty model must be a separate
prospective experiment, with all observations retained and failures visible.
