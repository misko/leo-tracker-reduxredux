This branch uses only existing DS24-0010/0011 recordings. The frozen `panel.json`
selects one original passing winner and one failed window whose maximum exported
fractional margin is in [0.0125,0.025), in each case × RX × CH7/8 group. The
nearest processed-scan midpoint probe start counter wins, then visit index.
The original maximum-margin candidate is retained (original rank breaks a margin
tie). Missing slots remain missing. There are 16 slots and 14 physical windows.
No position, orbit, error, or localization rank enters selection.

The existing verified `FastSegmentSource` reader is scoped to one local sequence
and fully exhausted, including containing-chunk integrity verification. Physical
paired-RX windows are read once. Before new analysis the historical production
detector must reproduce every exported candidate for both receivers, including
rank, timing, CFO, exact/control score, margin and gate. The established historical
runtime and parity tolerances are reused. No raw IQ copies or shared caches are
written. The job has one BLAS thread, a 580-second alarm and a 32-read maximum.

Primary comparison holds exported fractional timing and finalized CFO exactly
fixed. The tested `ChannelPilotWorkspace` compares one complex gain with eight
complex tone gains, independently per frame, with one independent complex DC
in each model. Every even-symbol-trained channel predicts odd symbols and vice
versa. In-sample explained fraction is descriptive. The result reports held-symbol
SSE and a paired frame-bootstrap interval (2,000 deterministic resamples). Positive
predictive support requires both the flat-versus-tone and the rolled-sequence-
versus-exact lower interval endpoints to exceed zero. This is a response diagnostic,
not an admission gate. Independent-channel-plus-noise, flat-plus-noise, wrong-
sequence and noise-only synthetic controls use 32 seeds each at exact known
timing/CFO. Their event uncertainty is reported; these controls do not calibrate
the pipeline GLRT false-positive rate.

A separately reported guarded-sample `FrameClock`/`WindowClock` diagnostic profiles
independent eight-tone channels with zero or one shared received-symbol-rate term.
Both compare the same guarded samples and even/odd symbol splits, with identical
carrier residual bounds ±120 Hz, fixed original timing, and a zero initial rate.
The received rate bound is ±100 ppm. This geometry omits DC and is separate from
the primary comparison; its SSE must not be compared directly with primary SSE.
The term represents received symbol/tone evolution against the sample grid, not
a transmitter-only clock. The existing independent analytic waveform generator
with scaled symbol boundaries validates known injected rate/CFO, random complex
channels and independent Gaussian noise. Wrong-sequence and noise controls remain
explicit.

All validation conditions on original full-window acquisition, which saw the
eventual held symbols. Within-window prediction does not withhold pipeline GLRT
data and is not an independent detection test. Frame bootstrap intervals are
descriptive because frame dependence has not been calibrated. The tiny panel
does not establish a false-positive rate or an absolute-CFO/localization gain.
Inference, admission, candidates and observations remain unchanged. No position
fitting is performed unless a measurement correction is subsequently justified.
