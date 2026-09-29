# Frozen fixed-position integration check

Use the same eighteen panels and q=0.20 training-selected coordinates/timings
as the published hard-cone scoring comparison, but change no cone weights.
The original independent-track trend mixture, sigma=100 Hz and background
slope scale=2000 Hz/s remain unchanged. Correct only the measured arrays using
the correction preparation protocol. All four arms use identical records,
candidate banks, training masks, coordinates and per-scan timing.

Arms: unchanged, symmetric, RX0 anchor, RX1 anchor. No selection between arms.
Verify unchanged training score, gradient, every track's held score and signal
candidate weights against the published q020 results to absolute tolerance
1e-7. Preserve all uncorrected tracks and bank eligibility exclusions. Report
bank-eligible coverage separately from the exported-track census.

Score held contrasts with calibration fixed from training. These conditional
per-track scores do not integrate calibration uncertainty or dependence from
shared donors; report descriptive paired scores, not independent trials or
calibrated joint confidence. The correction is a translation with unit Jacobian
conditional on training, but its model assumptions and uncertainty remain.

Run six correction tests in the actual scoring interpreter before freezing.
One sequential worker, BLAS1/nice19, 90 seconds and 4 GiB per child, at least
5 GiB available RAM before launch. No failed process is silently retried.
Every source and input is hash-bound before launch and checked afterward.

This is a scoring-only integration stage. There is no geographic optimization,
new location error, beam/direction calibration or sub-km claim. All outcomes
will be retained before deciding whether geographic refitting is justified.
