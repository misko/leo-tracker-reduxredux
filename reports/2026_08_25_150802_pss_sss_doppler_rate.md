# PSS/SSS Doppler-rate comparison for dwell `150802`

## Outcome

Over the dense opening six seconds of
`cap-20260825T150802-473cb5bbcbd6`, the exact PSS gives a rough Doppler-rate
point estimate of **-2.934 kHz/s**.  The narrow SSS slice, when evaluated at
the independently recovered PSS frame timing, gives **-3.644 kHz/s**.  The
persisted positive GLRT20ms probes give **-3.2657 kHz/s**.

The two sync-symbol point estimates differ from GLRT by only +0.331 kHz/s
(PSS) and -0.378 kHz/s (PSS-timed SSS), but they are not independently precise:
their six-point 95% regression intervals include zero.  They are supporting
rate evidence, not a replacement for the known-pilot GLRT trajectory.

Independent SSS acquisition is rejected.  Its fitted epochs agree with the
PSS/GLRT frame epoch in 0/6 seconds and produce a nonsensical +134 kHz/s rate
with 452 kHz RMS residual.  The useful SSS number above is explicitly
PSS-timed and must not be described as an SSS-only acquisition.

## Results

| Estimator | Timing source | Rate (kHz/s) | 95% OLS interval (kHz/s) | Delta from GLRT (kHz/s) | CFO bias vs GLRT line (kHz) | CFO RMSE vs GLRT line (kHz) |
|---|---|---:|---:|---:|---:|---:|
| GLRT20ms | GLRT per probe | **-3.2657** | [-3.2676, -3.2639] | reference | reference | reference |
| Exact PSS | independent PSS fit per second | **-2.934** | [-9.691, +3.822] | +0.331 | +10.3 | 13.2 |
| Narrow SSS slice | PSS frame timing | **-3.644** | [-8.688, +1.400] | -0.378 | -29.3 | 30.0 |
| Independent narrow SSS | independent SSS fit per second | +134.3 | [-233.1, +501.6] | +137.5 | -655.5 | 830.1 |
| Upper-edge PSS control | correct lower-edge PSS timing | +1.564 | [-10.495, +13.624] | +4.830 | +689.1 | 689.3 |

The GLRT fit uses 240 silver-positive 20 ms probes (40 per second, sampled at
25 ms cadence) with GLRT64 exact-minus-control margin at least 0.05.  Its OLS
standard error is 0.00094 kHz/s.  That very narrow statistical interval does
not include systematic receiver or waveform-model error.

All three estimates are slopes of observed receiver CFO.  Their comparison is
valid because they share one radio path and time interval, but without an
independent oscillator calibration the slope cannot be attributed exclusively
to spacecraft Doppler rather than residual LNB/receiver drift.

The six per-second frequency peaks were:

| Second center (s) | PSS CFO (kHz) | PSS-timed SSS CFO (kHz) | GLRT mean CFO (kHz) |
|---:|---:|---:|---:|
| 0.5 | 395.437 | 347.081 | 379.668 |
| 1.5 | 376.851 | 351.945 | 376.380 |
| 2.5 | 382.218 | 337.414 | 373.097 |
| 3.5 | 376.968 | 351.370 | 369.839 |
| 4.5 | 392.102 | 337.243 | 366.586 |
| 5.5 | 366.796 | 327.602 | 363.337 |

## Method

The input, receiver path, and exact-PSS acquisition are the same frozen,
read-only inputs used in the preceding PSS/SSS/GLRT20ms comparison.  Each
one-second PSS fit is independent and supplies one frame epoch.  At 2.5 MS/s,
both the captured PSS and lower-edge SSS slice contain only 11 complex samples
per 1.333 ms frame.

Inter-frame carrier phase was tested first and rejected: adjacent-frame PSS
and SSS phase coherence was only 0.004--0.053, and the unwrapped increments
were dominated by near-pi jumps.  A rate obtained from that phase would be an
arbitrary unwrap result.

The accepted exploratory estimator is invariant to frame-to-frame phase
resets.  For every candidate frequency `f`, it averages normalized matched
power over the 750 sync symbols in a second:

`M(f) = mean_k |<x_k, s exp(j 2 pi f n / Fs)>|^2 / ||x_k||^2`.

The bank spans -1.2 to +1.2 MHz in 2 kHz steps; the maximum is refined with a
three-point log-parabolic interpolation.  A straight line is then fitted to
the six one-second frequency peaks at their block centers.  SSS uses the next
11-sample symbol at the PSS-derived frame epoch.  The independent-SSS control
instead uses each second's own SSS maximum.

The PSS frequency-bank peak/median ratios decline from 1.81 to 1.61 over the
six seconds.  PSS-timed SSS declines from 1.73 to 1.21.  The short templates
make the frequency objective broad, which is reflected in the large
second-to-second residuals and rate intervals.

## Interpretation

- **GLRT20ms is the defensible Doppler-rate measurement:** -3.2657 kHz/s over
  the dense six-second segment.
- **PSS supports that rate only coarsely:** -2.934 kHz/s, about 10% shallower
  in magnitude, with an interval too wide to exclude zero.
- **SSS supports it only after PSS supplies timing:** -3.644 kHz/s, about 12%
  steeper in magnitude.  Independent narrowband SSS still fails acquisition.
- Agreement of the two sync point estimates with GLRT is encouraging, but the
  11-sample bandwidth-limited slices do not supply a precise standalone
  Doppler-rate observable in this dwell.

No path beneath `/mnt/qnap01` was written, no Standard product or golden
fixture was changed, and no new RF collection was performed.

## Evidence

- [Machine-readable comparison](figures/2026_08_25_150802_pss_sss_doppler_rate/comparison.json)
- [Detection comparison that established the PSS/SSS timing claims](2026_08_25_150802_pss_sss_glrt20ms.md)
