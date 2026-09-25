# Track-conditioned PSS precision lock

## Result

Track conditioning and inter-frame PSS phase produce a materially tighter
local lock on the four reconstructed PSS tracks.

Across the four tracks:

- the median pointwise median absolute CFO difference from GLRT improves from
  6.261 kHz to 1.850 kHz;
- the median pointwise CFO RMSE improves from 12.575 kHz to 2.228 kHz;
- the median formal within-visit carrier-phase slope uncertainty is 1.85 Hz;
- independent even/odd PSS frame sets reproduce the visit-center timing lock
  to 121 ns median absolute difference and 183 ns median RMS; and
- each visit contributes a median of 90 PSS frames.

The refinement improves local precision, not absolute accuracy.  The long-term
PSS-minus-GLRT CFO error still has a slope, and the median absolute Doppler-rate
difference remains approximately 0.52 kHz/s.  The very small within-visit
carrier uncertainty must therefore not be presented as absolute-Doppler
accuracy.

| track | visits | even/odd timing difference | carrier slope sigma | prior median CFO error | refined median CFO error | refined RMSE | refined rate difference |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | 34 | 95 ns | 1.68 Hz | 4.474 kHz | 1.019 kHz | 1.169 kHz | +0.208 kHz/s |
| 3 | 42 | 127 ns | 1.88 Hz | 7.819 kHz | 4.713 kHz | 5.912 kHz | +0.918 kHz/s |
| 4 | 33 | 153 ns | 1.82 Hz | 5.677 kHz | 2.599 kHz | 3.015 kHz | -0.643 kHz/s |
| 5 | 25 | 114 ns | 1.94 Hz | 6.846 kHz | 1.101 kHz | 1.440 kHz | +0.401 kHz/s |

## Method

The input is the four PSS timing tracks reconstructed in
`2026_09_25_five_glrt_tracks_pss_reconstruction.md`.  Track membership and the
coarse PSS mode are frozen before this stage.

For each 120 ms visit, the refinement:

1. reproduces the exact associated PSS mode from frozen IQ;
2. performs robust linear timing fits over the approximately 90 fractional PSS
   frame measurements;
3. repeats the timing fit independently on even and odd frames;
4. fits the inter-frame PSS correlation phase to obtain a carrier residual
   modulo the 750 Hz frame rate; and
5. lifts that 750 Hz ambiguity using only the prior PSS carrier trajectory.

GLRT is used only after the PSS result is frozen, for the reported comparison.
A single constant CFO offset is removed per track; this does not change CFO
rate or the visible time-dependent residual.

The even/odd comparison is the primary empirical timing-repeatability metric.
It avoids claiming that sub-sample interpolation or averaging automatically
provides corresponding physical accuracy.

## Interpretation

This supports a two-stage PSS lock:

- **Acquisition:** the existing blind CFO bank and PSS-only timing association;
- **Tracking:** predicted timing gates plus an inter-frame carrier-phase
  discriminator, with periodic blind reacquisition.

The tracking stage can narrow the carrier estimate from several kilohertz to
roughly the 1--5 kHz agreement scale observed here while reporting a very
precise local phase slope.  Timing repeatability is approximately 0.1--0.2
microseconds on these 10 MHz edge slices.

Three limitations remain:

1. The PSS carrier has unresolved 113.636 kHz and 750 Hz branches.  The refined
   lock is conditional on a continuous PSS trajectory.
2. Tracks 3 and 4 retain systematic PSS-versus-GLRT CFO-rate differences.
   Inter-frame phase reduces jitter but cannot remove estimator-model bias.
3. Timing is template-relative.  Unknown analogue passband phase, multipath,
   LNB/receiver delay, and sample-clock error prevent a calibrated absolute
   arrival-time claim.  A measured complex front-end response is needed before
   treating approximately 100 ns repeatability as approximately 100 ns
   absolute accuracy.

The defensible result is therefore a **more precise PSS tracking lock**, not a
new absolute time or isolated spacecraft-Doppler observable.

## Artifacts

- `figures/2026_09_25_pss_precision_lock/pss-precision-lock.png`
- `figures/2026_09_25_pss_precision_lock/precision-lock-points.csv`
- `figures/2026_09_25_pss_precision_lock/summary.json`
- `figures/2026_09_25_pss_precision_lock/refine.py`
