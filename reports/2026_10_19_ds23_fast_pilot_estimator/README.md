# Bounded continuous known-pilot CFO fitting

The final fitter takes 4.937 seconds versus the reference grid's 15.004 seconds
on the same 96-probe 2.5 MHz development panel: approximately 3.04 times faster
for core fitting. Maximum CFO difference is 1.249 Hz. No point's normalized
projection score regresses by more than 1e-6; the minimum difference is
-2.512e-7. Both methods flag one epoch boundary and no carrier/rate boundaries.
This is neither an embedded benchmark nor a full-pipeline runtime estimate.

The likelihood, pilot template, three fitted parameters, per-frame complex
gains/DC and nominal frequency scout are the same. The continuous variant
uses analytic projected derivatives and a bounded damped 3x3 normal solve.
The final score is independently evaluated through the reference scorer.
Template construction is warmed before timing, and method order alternates.

This panel was reused while optimizing the implementation. The slower
three-start and initial one-start results and exact source versions remain
preserved; the panel is not untouched accuracy validation. A separate real-IQ
qualification includes adaptive 2.5/10 MHz captures. Synthetic tests cover
projected derivatives, gain/DC nuisance elimination, both pilot edges and
high signed carriers at 10 MHz.

See the [full RX2 measurement cohort](../2026_10_19_ds23_rx2_measurement_cohort/README.md)
for format qualification, all original twenty development scans, matched
position comparisons, boundary fallbacks, source inventories and the lossless
evidence archive containing this benchmark's plans and all three fit versions.
No raw IQ is published. A higher in-sample pilot score does not prove a more
accurate carrier estimate or a more accurate position.
