# Frozen matched cross-visit frequency prediction

Use the same 18 receiver tracks selected in the training-waveform experiment;
do not rank on its outcomes. For each select A, the earliest original training
observation; B, the earliest training observation at least two seconds after A;
and H, the earliest original held observation after B. If unavailable, report
unsupported and do not replace the track. Use cached public candidate bindings
and the first eight complete frames from each 20-ms probe.

Reuse hash-verified A excerpts when bindings agree; extract B/H through public
read-only ports. Permit at most three 120-second extraction invocations, with
atomic checkpoints. No new RF or multi-hour campaign. Numerical work has a
120-second cap, one process/thread.

Compare linear extrapolation through A/B using (1) cached carrier frequency and
(2) cached plus the long-pilot residual fit, with the existing fixed ±1500 Hz
search and symbols22–221. Frequency is actual tuned RF plus candidate CFO plus
residual; subtract A's actual RF for numerical conditioning. Use observation
support-center times from the frozen track. Neither H samples nor H cached CFO
contribute to the A/B trajectory. H cached CFO only establishes the demodulator's
frequency reference when evaluating the independent prediction.

At H, score both predicted frequencies against the SAME pilot observations:
calibrate per-frame/carrier gains on22–221 and predict222–301. Keep all eight
frames, failures, weak signals and bounds. Also report cached H and a local
long-pilot H fit as descriptive controls, not selection or training signals.
Use the corrected deterministic upconversion phase convention. Report paired
equal-track NMSE and prediction changes, per dataset and pooled. No quality
gating or tuning after results. Reject unsupported edge changes explicitly.

This is a local smoothness/pilot-prediction test, not orbital truth, verified
satellite identity, deployment benchmarking, or geographic accuracy. Upstream
track construction and exposed panels remain inherited conditioning. If gains
are inconsistent, do not promote to localization on this evidence alone.
