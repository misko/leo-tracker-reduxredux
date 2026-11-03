# Carrier agreement does not qualify the local frequency-rate correction

**Do not promote this stability weight.** Separate pilot carriers frequently agree on a rate that does not improve the next frames. Multiplying the donor-calibrated correction by their agreement slightly worsens pooled prediction relative to the preceding reduced-rate model and leaves DS8 worse than constant frequency.

| Dataset | Median carrier agreement | Targets improved / worsened / unchanged vs constant | Mean gain vs constant | Mean gain vs reduced rate |
|---|---:|---:|---:|---:|
| DS7 | 0.688 | 38 / 14 / 8 | +0.002477 | −0.000721 |
| DS8 | 0.801 | 20 / 24 / 16 | −0.001965 | +0.000498 |
| DS9 | 0.713 | 28 / 10 / 2 | +0.001983 | −0.000372 |

Positive gain means lower held complex-pilot NMSE. All 160 target receiver-frames remain: 86 improve, 48 worsen and 26 are unchanged versus constant. Mean gain versus constant is +0.000688, smaller than the preceding reduced-rate model's +0.000864. The paired change versus that model is **−0.000177**. These are small waveform-prediction differences, not measured Doppler errors or geographic accuracy gains.

DS8 has the highest median carrier agreement, yet remains adverse. A supplementary descriptive slice at agreement ≥0.8 contains 15 DS8 blocks with mean gain −0.003387 versus constant. This slice was inspected after execution and does not select outputs or establish a validated threshold. It illustrates why agreement alone cannot certify useful extrapolation.

## Frozen method

The [protocol](PROTOCOL.md) preceded execution. Retain the 80 evaluation blocks from [donor-calibrated shrinkage](../2026_09_29_rate_transfer/README.md), with its inherited strengths: DS7/DS8 0.5 and DS9 0.25. No new strength fitting.

All caches have eight pilot columns. Split them into alternating columns `[0,2,4,6]` and `[1,3,5,7]`, preserving their recorded order. Independently fit each subset's intercept and rate on symbols 22–221 of the first eight frames using the unchanged [chirp estimator](../2026_09_29_waveform_chirp/README.md). No held target samples enter these fits.

For qualified rates r0 and r1, define agreement `max(0, 2*r0*r1/(r0²+r1²))`. Both zero or either unqualified gives zero. This bounded heuristic is one for equal nonzero rates and zero for opposite signs; it is not a calibrated probability. Multiply inherited strength by agreement, and apply it to the full-carrier intercept displacement and rate. Forecast frames nine and ten, calibrating gains on their early symbols and scoring disjoint later symbols as before.

All 160 subset fits qualify. Zero agreement occurs in 4/30 DS7 blocks, 8/30 DS8 blocks and 1/20 DS9 blocks, producing 26 unchanged target predictions. No optimizer fallback or target exclusion occurred. Both constant and reduced-rate controls reproduce their parent results within 1e-10 NMSE for all 160 targets.

## What the result changes

The DS8 failure is not resolved by requiring cross-carrier consistency of the training rate. Shared effects can move all carriers together, and a locally consistent rate can cease to predict future frames. These data do not distinguish shared hardware/transmitter effects, changing signal content, acquisition artifacts or physical frequency evolution. Carrier subsets are disjoint observations but do not guarantee independent errors.

The immediate rate-stability heuristic has failed its intended transfer check. Preserve the constant estimator and the reduced-rate candidate for comparison, without promoting either carrier weighting or a dataset-specific correction. Further estimator tuning on the same small corpus is lower priority than identifying an independently constrained source of time-varying error that survives into the geographic inputs.

No independent Doppler truth, absolute timing, satellite identity or location fit is evaluated. The visits and their outcomes were already examined; this is exploratory computational holdout, not blind research validation. Reliable short-window subkm accuracy remains unproven.

## Verification and evidence

Two tests pass: agreement's sign, scale and boundary behavior; failed-fit fallback and rejection of nonfinite qualified rates. The parent estimator's tests cover signed rate recovery, held-sample isolation and analytic gradients. All parent/cache hashes verify, exact endpoint replays pass, and execution finishes within its 120-second cap. [results.json](results.json) stores every subset fit, agreement, applied strength, target score and dependency hash.

```sh
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python -m unittest discover -s reports/2026_09_29_rate_carrier_agreement -p 'test_*.py'
OPENBLAS_NUM_THREADS=1 timeout 120 uv run --no-project --with numpy --with scipy python reports/2026_09_29_rate_carrier_agreement/run.py
```

The writer uses exclusive creation; replay in a fresh output context. `evidence.sha256` seals the report, protocol, code, tests and results. No RF collection, archive export, production edit or remote publication occurred.
