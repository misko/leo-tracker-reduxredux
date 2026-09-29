# Half-rate full-analysis quality probe

This experimental Wave 4 wrapper selects every even IQ sample and every even
exact/control template sample without an anti-alias filter, then runs the full
22-window, eight-candidate pipeline at half the original sample rate.  The CLI
still accepts original rates and native original-length files.  Effective rates
are 1.25, 2.5, 3.75, and 5 MS/s.  CFO values remain in hertz; coarse, refined,
and final candidate epochs are multiplied by two on output for matching in
original-sample units.

The internal 20 ms analysis window contains `effective_rate / 50` samples and
the internal 120 ms dwell contains `effective_rate * 120 / 1000` samples.  The
owned test verifies all rate/length relations, even selection, epoch mapping,
and rejection of short source buffers under ASan/UBSan.  Template and dwell
decimation CPU is measured once and amortized into the 22 outer fused timers;
the existing per-window CI16-to-analysis conversion remains inside each timer.

This is explicitly an alias-prone approximation.  It may halve much of the
pipeline cost but can fold out-of-band energy into every detector stage and
change SNR.  It is not a production configuration.  The first quality gate is
the established 32-dwell host panel and must recover at least 829 of 843 hits.
Only a passing result justifies the 704-dwell cohort or ARM timing.

## Host gate result

The sealed 32-dwell run failed the gate: it recovered 551/843 reference hits
(65.36%), with 956 native positive candidates.  Recovery by original rate was
57/205 at 2.5 MS/s, 108/152 at 5 MS/s, 203/258 at 7.5 MS/s, and 183/228 at
10 MS/s.  The experiment therefore stops before the 704-dwell cohort and ARM
execution.  Evidence is in `host32/{manifest,summary,standard-audit}.json`.

The especially poor lowest-rate result is consistent with more than output
epoch scaling alone.  The half-rate scorer produced only 101 positive
candidates where the reference produced 205 at 2.5 MS/s.  Also, original
per-frame starts use `round(original_rate * frame / 750)`, while rebuilding the
geometry at half rate and multiplying by two can move a physical frame start
by one original sample.  A single even-sample template cannot follow that
frame-dependent parity.  Aliasing, lost sample energy, changed proposal lags,
and this parity mismatch are all present in this simple experiment, so the
result does not isolate one cause.  A follow-up would have to retain full-rate
proposals and preserve original physical frame starts before attributing the
loss to half-rate scoring itself.
