# Past-frame shared differential phase-drift transfer

Use the eight existing cached pilot visits and both receivers (80 frames each).
Verify upstream cache and input hashes. Reconstruct each carrier's MHz offset
from the original pilot-band geometry, RF mask and cached acquisition CFO.

For each visit/RX jointly fit a single differential phase drift and independent
frame frequencies/gains on frames 0–29, symbols 22–221. Initialize frequencies
from existing full-support global peaks. Keep frequency corrections within
±1500 Hz and drift within ±300 ppm, matching earlier drift bounds. Minimize
mean per-frame normalized residual after profiling static complex carrier gains.
No sequence state, target frame or later symbol participates in this drift fit.

Freeze drift for frames 30–79. On each later frame fit only frequency and
static carrier gains using symbols 22–221, then predict symbols 222–301.
Compare zero drift, frozen drift and sign-reversed frozen drift with identical
frequency initialization/bounds. Unqualified shared fits fall back to zero
drift, retaining every evaluation case. Qualify by optimizer success, no drift
or frequency boundary (within 1 unit), and maximum gradient below 1e-5.

This effective differential phase parameter is not a calibrated oscillator,
sample-rate, orbital Doppler, UTC or range measurement. Cached acquisition and
these visits are previously examined. No geographic fit or new RF. A single
worker is capped at 120 seconds, preserving any failure without retuning.
