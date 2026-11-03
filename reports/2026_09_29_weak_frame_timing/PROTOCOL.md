# Weak-frame timing diagnostic

Freeze before execution. On S31 and S32, each RX uses the first four frames
below 0.03 explained energy and first four above 0.2 among frames 0–29 in the
preceding peak study. This is a posthoc diagnostic selection, not blind evaluation.
Retain all 32 receiver-frames, including strong controls.

Replay original digest-verified IQ. Search timing shifts of −2, −1, 0, +1, +2
OFDM symbols, each with −1, −0.5, 0, +0.5, +1 native sample offsets (25 trials).
Select by pilot coherence on symbols 22–121; fit frequency and static carrier
gains only there. Predict symbols 222–301 without refitting. Compare against
zero timing shift and a 17-symbol-rolled pilot template at the selected shift.
The wrong template receives its own training-only frequency/gain fit.

Measure raw IQ power in the same central frame interval and per-symbol FFT
pilot-band energy; do not equate unchanged total power with presence of the
particular desired signal. This bounded search does not exclude larger offsets,
sample-clock stretch, interference, alternate frame patterns or channel changes.
No frequency/clock correction is promoted solely for improving training fit.
