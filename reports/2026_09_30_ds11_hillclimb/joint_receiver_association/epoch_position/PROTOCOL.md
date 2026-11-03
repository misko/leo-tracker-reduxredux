# Soft timing association, family2 pilot

Freeze the window-balanced donor16 timing calibration before DS11 fitting.
Donor17 validation supports feasibility only; identities are inferred and
timing is not a ranging observable here. Use original0 and additional1, the
pre-existing family2 pilot members, without choosing records by their errors.
Compare unchanged Doppler with the timing factor, initialized at the original
IID solution, with identical bounded position/timing optimization.

For each owned cross-RX track pair, average timing-event log likelihood ratios
within observing windows, then across training windows. Exact duplicate waveform
pairs contribute once per window. Divide each edge by the larger endpoint degree
so a fragmented track cannot acquire arbitrarily many full-strength edges.
Add that finite coefficient only when both tracks select the same physical
satellite. Sum all assignments exactly; do not hard-link identities or prune.
This is a bounded composite association factor, not a calibrated joint density.
It contributes no direct range, angle, orbit correction or position derivative.
Outliers retain nonzero probability through the smoothed calibration.

Training uses training visits only. A zero-strength factor must reproduce the
existing Doppler score, gradient and expected source count. Check tiny assignment
enumeration, ownership, duplication and held-data isolation. Fit each arm in at
most90 seconds with one numerical thread; at most three workers. Seal fits and
source hashes before geographic scoring. Both timing fits must qualify and
improve their own original and refitted Doppler errors by at least5 percent
before extending this model to further acquisition settings. These two records
cannot establish general DS11 improvement. Retain all failed fits and baseline.
