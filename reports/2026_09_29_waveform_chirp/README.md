# Local frequency-rate forecasting across frames

**A free local frequency rate does not provide a transferable improvement.** It improves mean held waveform prediction on DS7 and DS9 but worsens DS8 enough to lose overall. Keep the constant-frequency baseline; no geographic accuracy improvement is established.

This is a different hypothesis from shared differential carrier drift: frequency evolves in time within each ten-frame block, with independent nuisance complex gains per frame/carrier. It does not require phase coherence between frames or semantic header decoding.

## Results

Fit the first eight frames of each block and forecast the last two. Target-frame early symbols calibrate nuisance gains, but do not refit the predicted frequency or rate. The scored symbols are disjoint from both frequency fitting and target-gain calibration. Lower complex-pilot normalized mean squared error (NMSE) is better.

| Dataset | Target receiver-frames | Constant mean NMSE | Linear-rate mean NMSE | Improved targets |
|---|---:|---:|---:|---:|
| DS7 | 60 | 0.785334 | 0.783267 | 34/60 |
| DS8 | 60 | 0.835734 | 0.846174 | 20/60 |
| DS9 | 40 | 0.753813 | 0.749313 | 27/40 |

Across all 160 targets, 81 improve and 79 worsen. Mean paired NMSE gain is **−0.002015**; median gain is +0.000056. Positive gain means lower error with the linear model. The mixed median and mean make the full distribution important; there is no consistent benefit.

| Visit | Improved / 20 | Mean paired NMSE gain |
|---|---:|---:|
| DS7 S02 | 13 | +0.002871 |
| DS7 S31 | 10 | +0.001375 |
| DS7 S32 | 11 | +0.001956 |
| DS8 S13 | 9 | −0.010294 |
| DS8 S28 | 4 | −0.011198 |
| DS8 S29 | 7 | −0.009829 |
| DS9 middle | 16 | +0.008000 |
| DS9 first | 11 | +0.000999 |

All 80 linear fits qualify, none requires fallback, and maximum scaled gradient is 1.16e-8. Fitted frequency rates span −15,468 to +16,775 Hz/s. They combine waveform, acquisition and hardware effects; they are not isolated orbital Doppler rates. Convergence does not certify physical interpretation.

## Method and verification

The [protocol](PROTOCOL.md) preceded execution. Reuse hash-verified pre-correction pilot caches from the eight visits in the [block-frequency experiment](../2026_09_29_block_frequency_support/README.md). Each RX contributes five fixed ten-frame blocks beginning at relative frames 30, 40, 50, 60 and 70. All 80 blocks and 160 targets remain, including weak frames; no outcome filtering.

Fit symbols 22–221 in the first eight frames. The constant arm uses a training-only 8192-point FFT initialization and scalar refinement. The rate arm starts there and profiles independent frame/carrier gains under phase `2π(f*u + rate*u²/2)`, using scaled analytic gradients. Its intercept bound is ±1500 Hz around the constant solution and rate bound ±100,000 Hz/s. Frame-slot spacing is 1/750 s. Effective frequency is ambiguous under sampled pilot geometry; the local rate search does not solve absolute aliasing.

Forecast frames nine and ten. Their symbols 22–121 fit gains only, and symbols 222–301 evaluate both models. Because target gains use contemporaneous samples, this is a frequency forecast with target channel calibration, not a completely observation-free complex waveform forecast.

Two synthetic tests pass: signed frequency/rate recovery with independent random frame/carrier phases and target-frame mutation isolation; analytic gradients against finite differences. The noiseless forecast error is below 1e-10. Existing input hashes verify; all fits complete within the 120-second execution cap. Results and dependency hashes are in [results.json](results.json).

## Consequence for subkm work

This test closes a specific constant-frequency limitation without claiming that physical Doppler rate is unhelpful. A free slope learned over roughly ten milliseconds has noisy leverage and extrapolates that uncertainty into future frames. The observed DS8 loss is consistent with that concern, but this assay does not isolate its cause.

Do not pass these free rates into geographic fitting. Any next rate model needs an independently justified constraint or a transferable training-only regularization rule, tested against this constant baseline on the same full population. Dataset-specific selection after observing these results would be exploratory tuning. The existing sequence/phase experiments and this result do not yet support a general frequency-estimation upgrade for localization.

These are previously examined, selected visits with dependent frames and receivers; no independent Doppler truth, absolute timing, satellite identity or geographic accuracy was evaluated. No RF collection, raw archive export, production modification or remote publication occurred. Reliable short-window subkm accuracy remains unverified.

## Reproduce

From repository root, using the existing caches:

```sh
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python -m unittest discover -s reports/2026_09_29_waveform_chirp -p 'test_*.py'
OPENBLAS_NUM_THREADS=1 timeout 120 uv run --no-project --with numpy --with scipy python reports/2026_09_29_waveform_chirp/chirp.py
```

The numerical writer creates `results.json` exclusively to preserve evidence; replay in a fresh output context. `evidence.sha256` seals report, implementation, tests, protocol and numerical output.
