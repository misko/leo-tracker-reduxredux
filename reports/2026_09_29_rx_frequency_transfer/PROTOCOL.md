# Paired receiver frequency transfer

Freeze before execution. Use the eight raw-IQ visits from the longer-sequence
assay, both RXs, first 80 complete frames. Require cached frame origins to agree
within 0.1 ms and matching sample rates/edges; do not silently align aliases.
These recordings were examined before and are not independently labeled emitters.

Re-demodulate raw IQ, estimate frequency from pilots 22–221 and evaluate
complex predictions on pilots 222–301. Per-carrier gains use 22–221 only.
Combine cached acquisition CFO plus demodulated residual frequency to put RX
estimates on the same within-visit frequency convention. Common FFT grid effects
cancel in RX differences; this is not calibrated orbital Doppler.

First 30 frames estimate one median RX1-minus-RX0 offset; remaining 50 frames
evaluate. Test a 50/50 blend of each RX's own frequency with the simultaneous
peer frequency after applying the frozen offset. Fit no target-frame correction
from held pilot samples. Compare own-only, calibrated blend, zero-offset blend,
and a peer-frame control rotated by 13 within evaluation frames.

Qualification is diagnostic only: median training pilot-initialization coherence
>0.5 on both RXs and median absolute deviation of training differences <100 Hz.
Retain every visit and all evaluation frames regardless. The shuffle control is
offline and is not a causal correction. No satellite labels or reference position
enter any fit. Report offset, training dispersion, held difference residuals,
paired wave prediction error and controls per visit/RX. Do not claim receiver
clock calibration, verified common emitter, or geographic accuracy from this alone.
