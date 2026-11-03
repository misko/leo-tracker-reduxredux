# Sharing differential phase drift across past frames does not improve prediction

Do not promote this phase-drift correction into geographic fitting. After a
numerical scaling audit, the shared-drift model improves 379/800 later-frame
held-pilot predictions and worsens 421/800. Mean paired NMSE gain is
−0.0000279 and median gain −0.00000149. These tiny mixed changes do not establish
a useful frequency, sample-clock or position-accuracy improvement.

| Dataset / visit | Improved / 100 | Median paired NMSE gain | Mean paired NMSE gain |
|---|---:|---:|---:|
| DS7 S02 | 55 | +0.0000333 | +0.0000555 |
| DS7 S31 | 44 | −0.00000429 | +0.0000124 |
| DS7 S32 | 41 | −0.0000524 | −0.0000706 |
| DS8 S13 | 41 | −0.0000187 | −0.0000229 |
| DS8 S28 | 50 | approximately 0 | −0.0000187 |
| DS8 S29 | 44 | −0.0000856 | −0.0001914 |
| DS9 middle | 43 | −0.0001308 | −0.0000413 |
| DS9 first | 61 | +0.0000480 | +0.0000535 |

Positive gain means lower held complex-pilot prediction error than zero drift.
Baseline median NMSEs range from 0.634 to 0.880. Each visit contributes two
receivers and 50 evaluation frames per receiver. Frames and receiver pairs
are dependent, and these visits have been examined in earlier research.

## Transfer hypothesis

Earlier sequence-assisted fits found an underconstrained per-frame differential
phase parameter. This test asks whether estimating one parameter jointly from
30 past frames makes it transferable. It reuses hash-verified cached pilots
derived from original IQ with no new collection. Carrier offsets are reconstructed
from the original pilot geometry, sample-rate mask and acquisition CFO.

For each visit/RX, jointly fit one drift and 30 independent frame frequencies,
profiling static complex gains separately for every frame/carrier. Only symbols
22–221 of frames 0–29 enter this fit. The phase convention is:

```
phase = 2π × symbol_time × (frame_frequency_hz − carrier_offset_mhz × drift_ppm).
```

Freeze drift for frames 30–79. Fit only frequency and static gains on each new
frame's symbols 22–221; predict symbols 222–301. The zero-drift and sign-reversed
drift controls use the same frequency initializations, bounds and samples.
This is transfer of drift across time, with contemporaneous frequency fitting,
not prediction of a future frame's complete frequency without observations.

All 16 shared fits qualify after audit; no evaluation frames are dropped.
Fitted effective drifts range from −19.82 to +9.32 ppm. They combine possible
transmitter, receiver and demodulation effects and are not calibrated sample
oscillator estimates. Static gains absorb carrier phase offsets; no absolute
frame start, UTC, satellite identity or range is estimated.

## Optimizer audit and preserved primary results

The [primary protocol](PROTOCOL.md) predates execution. The primary run qualified
all fits, but three stopped almost at their zero-drift initial point. Physical
Hz/ppm coordinates can make an optimizer's objective-change stopping test too
permissive on weak objectives. The primary output is preserved in
[results.json](results.json) and [summary.json](summary.json): 315 improvements,
335 deteriorations and 150 numerical ties at 1e−10 tolerance, with mean gain
−0.0000265. It is not overwritten by the audit.

The explicitly supplementary [scaling audit](scaled_audit.py) reoptimizes the
same training objective from those endpoints with 1000-Hz and 100-ppm parameter
scales. Bounds, physical model, source samples and held comparison remain fixed.
The numerical change is applied to all groups, not selected by held outcomes.
The three almost-zero drifts become +0.634, −0.669 and −0.028 ppm. All scaled
fits qualify, maximum scaled gradient 1.04e−7. The largest training objective
improvement is only 7.82e−8, and the aggregate adverse held conclusion remains.
The table above uses this supplementary, more carefully optimized result.

Sign-reversed drift loses to learned drift in 428/800 cases, but learned drift
still loses to zero drift in the majority. Beating an intentionally reversed
correction is insufficient evidence for replacing the baseline.

## Verification and limits

The synthetic test verifies signed drift recovery, analytic gradients against
finite differences, near-zero held prediction error on known data and isolation
from mutated held symbols. The raw-cache and upstream input hashes verify,
16 group memberships and all 800 evaluation frame memberships are retained,
and Ruff passes. The primary run completed in 1.65 seconds; primary and
supplementary commands both exit zero within their 120-second caps.

Cached acquisition initially used the recorded waveform, so the pipeline is
acquisition-assisted, not prospectively independent end to end. The local
frequency bounds and one shared drift per visit do not cover arbitrary frame
formats, overlapping emitters or faster drift. This negative result is scoped
to the tested model and corpus, not proof that sample-clock calibration is
irrelevant to navigation.

No geographic fit, RF collection, production edit or publication occurred.
This closes the immediate shared-phase-drift hypothesis without adding another
unsupported calibration parameter to localization. Preserve the existing
frequency estimator and pursue corrections only when they improve independent
waveform or track predictions.

See [scaled results](scaled-results.json), [scaled summary](scaled-summary.json),
[model](model.py) and [study](study.py). Artifacts are local. Reproduction uses
`study.py` followed by `scaled_audit.py` under NumPy/SciPy in a fresh output
context; numerical outputs use exclusive creation.
