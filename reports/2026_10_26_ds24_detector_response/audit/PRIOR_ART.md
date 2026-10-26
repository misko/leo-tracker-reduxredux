# Relevant prior estimator work

Continuous known-pilot refinement and effective timestamps already exist in
`tools/local_pilot_refinement.py`, `tools/fast_local_pilot_refinement.py`,
`tools/remeasure_ds23_rx2_cohort.py` and
`tools/probe_ds23_refined_timestamps.py`. The older local likelihood uses
nearly complete frames with per-frame complex gain/DC projection; continuous
CFO, fractional epoch and code-rate fitting are not new ideas here.

The published DS23 refined-precision report records an asymmetric-envelope
closure with opposite 2,000 Hz/s chirps agreeing within 0.2 Hz with its local
information-time prediction. This validates that local calculation, not the
historical deployed estimator's effective timestamp. Its refined curve can
still have substantial adjacent residual correlation at roughly 11–16 Hz RMS.
The 322-curve RX2 cohort also improved frequency scatter without establishing
a qualified cohort position gain.

The distinct current question is the exact deployed scope64 response. That
scorer uses symbols 2..65 of epoch-dependent complete frames, sums coherent
power within frames and returns acquisition CFO plus a gridded residual. A
candidate-fixed continuous maximum of this exact score can isolate grid
quantization from acquisition behavior without changing the pilot aperture,
epoch, source count, graph or satellite assignment. It must be compared with
the old full-frame estimator rather than presented as generic continuous
refinement for the first time.

The inherited one-source control has a 200 Hz/s chirp and 20 ms windows. A
midpoint-to-endpoint time change can account for at most 2 Hz of instantaneous
CFO, below its approximately 16.5 Hz graph RMS. Timestamp correction alone
therefore cannot explain that entire controlled error. No inference follows
about field bias, calibrated uncertainty or source multiplicity.

This review reads saved sources/reports only. No detector, propagation,
optimization or new IQ processing was performed by the auditor.
