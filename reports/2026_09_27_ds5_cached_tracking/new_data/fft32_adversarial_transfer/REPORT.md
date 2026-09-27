# FP32 transfer on adversarial proposal controls

The unchanged strided FP32 FFTW detector passed the preregistered numerical
identity gate against stable packed FP64 V4 on all 40 receiver cases. Both
methods produced 32 positive labels. Every FP64 positive associated with the
FP32 result within 2 microseconds and 8 kHz; there were no lost reference
positives, added candidate positives, selected-window changes, rank-order
changes, or projected-epoch changes.

The largest first-proposal FP32/FP64 difference was
`0.0000038646` microseconds in circular timing and `0.000034531` Hz in CFO.
Rank scores were identical at the precision returned by the wrapper.

Both methods associated a fractional-complete proposal with an injected pilot
in all 32 pilot-bearing receiver cases. In each equal-power two-pilot case the
single returned proposal associated with trajectory `a`; trajectory `b` was
not returned because the frozen run allowed only one candidate. The
pilot-plus-strong-tone cases associated with the injected pilot on both
receivers at both rates. Noise and tone cases produced no detector-positive
labels, but this report does not interpret their proposals as false alarms.

Per-rate results were identical: 12/12 simple pilot receiver cases, 2/2
two-pilot receiver cases, and 2/2 pilot-plus-tone receiver cases were positive
and matched; the two noise and two tone receivers were negative for both
methods. Injected presence did not define the positive label and was scored
separately from detector identity.

This is a one-call science comparison and contains no performance timing. The
FP64 result is a numerical reference rather than physical truth. The challenge
uses constructed Qin pilot-only signals with flat channels and omits unknown
QAM/data, so passing it does not establish full real-signal robustness.
