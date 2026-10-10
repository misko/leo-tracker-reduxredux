# FFT-bin likelihood: valid approximation, not an exact observation model

Source and published-report review only. No recordings, models, new outcomes,
tests or reference coordinates were accessed. No launch is proposed.

The current native exact-template GLRT selects the maximum of 512 spectral
power bins. `presence.c` reports residual CFO as signed winning index divided
by `512 * SYMBOL_S`, with `SYMBOL_S = 4.4e-6`. The corresponding grid spacing
is approximately **443.892 Hz**, with uniform rounding RMS approximately
**128.137 Hz**. This is close to the positioning likelihood's fixed 125 Hz
width, so quantization plausibly explains much of that width for strong,
full-support signals. It does not establish the width's historical rationale
or calibrate its value for real recordings.

The spacing is set by symbol period and FFT size, not directly by sample rate.
Sample rate changes symbol sample locations, interpolation and available
support. Python `_glrt_pair_fft` uses `fftfreq(size, symbol_step_s)` and selects
the actual maximum; native uses the same nominal-symbol grid. Historical
backend/build support policies still require exact source binding.

## What the persisted observation means

Native tracking CFO is acquired CFO plus the exact-template winning residual
bin. Python `_score` has the same additive composition. Fractional epoch
processing changes the correlation workspace, not that additive frequency
definition. The acquisition CFO itself is data-selected and need not lie on
the residual-bin lattice. A bin's physical interval therefore has its own
acquired-CFO origin; it is not a universal rounding grid on absolute CFO.

`project_scanner_candidates` passes persisted fractional tracking CFO to
`prepare_position_windows` as `measured_hz`. Actual RF is a separate field,
used by orbital Doppler and receiver RF-stretch predictions. No RF-edge mixing
frequency is added to the stored tracking CFO by this positioning projection.
Acquisition demodulation and RF tuning conventions must remain unchanged;
one must not integrate a cell around an RF-adjusted value twice.

## When a CDF difference would be normalized

If an assumed latent continuous estimate is `Y ~ Normal(mu, tau²)` and the
reported value is its nearest-bin rounding on a *known fixed origin*, then
the observation probability for bin j is

`P(j | mu) = Phi((b_j+Delta/2-mu)/tau)
           - Phi((b_j-Delta/2-mu)/tau)`.

For the existing circular-frequency mixture, sum the wrapped Gaussian bin
mass over alias images and use clutter mass `Delta/ALIAS_HZ`. Preserve the
visibility/event normalization and mixture weights. A density-equivalent
version divides every bin mass, including clutter, by Delta; the resulting
per-observation constant cannot affect parameter selection. Handle the alias
seam and cell endpoints explicitly. Stable CDF/log-CDF differences are needed
in tails. This is computationally cheap compared with orbit prediction.

The residual-bin period `1/SYMBOL_S` and the position likelihood's source-defined
alias period are different concepts. Do not replace the latter with the FFT
period, assume its bins tile it exactly, or normalize an arbitrary truncated
set of residual bins as if it were a full tracking-frequency quantizer.

## Why argmax does not prove rounding

Actual native output is `argmax_k sum_frames |FFT(correlations)_k|²`.
This is not generally the rounded value of a Gaussian continuous estimator.
Its distribution depends on competing correlated spectral powers, support,
SNR, template match, interfering peaks and the data-selected acquisition origin.
Even a continuous score maximum need not have the discrete winner as its
nearest bin when the peak is asymmetric or there are competing modes.
An exact bin-selection likelihood would require a model for those competing
powers, not only a CDF difference around the observed winner.

The 125 Hz width cannot simultaneously be treated as latent continuous noise
and as quantization RMS without double-counting. A CDF model needs an independently
specified latent tau; setting tau to zero gives nearly flat likelihood inside
a cell and sharply changing boundaries, not a high-information smooth Gaussian.
Choosing tau from position errors would be leakage. Persisted scalar GLRT margin
does not identify the latent noise or competing-power distribution.

## Existing evidence and recommendation

[125 synthetic results](../2026_10_09_position_error_iter125/RESULTS.md) reduced
strong full-support CFO RMS from 125.55 Hz to about 11.6 Hz, but partial/short
bursts retained large errors. This supports quantization as a major contributor
in that restricted case, not a universal observation law.
[133's real matched pilot](../2026_10_10_position_error_iter133/DECISION.md)
improved fitted-c mean by only about 13 m and worsened median by 191 m; six
recordings improved and six regressed. Removing bin rounding did not broadly
solve typical localization error.

Bin integration is mathematically distinct from replacing a winning bin with
a refined point: it represents uncertainty over a latent estimate. However,
the current estimator contract does not establish its rounding assumptions or
latent variance. **Do not launch a localization comparison as an exact physical
CDF model now.** At most, a future source-bound synthetic estimator-distribution
test could falsify the fixed-origin rounding approximation under declared SNR,
support and interference conditions, before any position fit. No new parameter
sweep or covariance claim is justified by the existing evidence.

Source links: [native GLRT](../../src/leo/analysis/native_presence/presence.c),
[pilot grid/composition](../../src/leo/analysis/starlink/pilot_methods.py),
[candidate projection](../../src/leo/application/scanner_trajectory.py),
[position input composition](../../src/leo/application/regional_position_inputs.py).
