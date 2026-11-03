# Noncoherent block fitting already suppresses most weak-frame frequency influence

**Do not promote support-based frequency weighting as an accuracy improvement.**
In a matched multi-frame fit, removing unsupported frames changes the estimated
frequency by at most **0.741 Hz** and does not improve mean held prediction error
through the frequency change. A small gain remains from explicitly abstaining on
unsupported waveform predictions, which is a different benefit.

All eight existing visits, both receivers and evaluation frames 30–79 are kept:
five fixed ten-frame blocks per receiver, **80 blocks / 800 receiver-frames**.
Ten frames span about 13.3 ms of frame slots. No phase coherence between frames
is assumed. No raw collection, production edit, or position fit was performed.

| Visit | Retained frames / 100 | Maximum block frequency change | Mean held NMSE gain: frequency weighting only | Mean gain: weighting plus abstention |
|---|---:|---:|---:|---:|
| DS7 S31 | 71 | 0.631 Hz | −0.0000008 | +0.0012564 |
| DS7 S32 | 79 | 0.741 Hz | −0.0000085 | +0.0012208 |
| Other six visits | 600/600 | 0 Hz | 0 | 0 |

Positive gain means lower error. The frequency-weighting changes are negligible
and slightly adverse in the mean for both affected visits. All 60 blocks from
the other six visits are exactly unchanged. None of the 80 blocks is empty.
All 50 unsupported frames remain in the reported scoring.

## Matched comparison

The [protocol](PROTOCOL.md) was frozen before execution. Each block estimates
one common frequency from symbols 22–221 using a sum of squared per-frame,
per-carrier correlations. A separate constant complex gain for each frame/carrier
absorbs unknown phase and amplitude. An 8192-point FFT initializes frequency;
local refinement uses the same profiled objective. Symbols 222–301 are withheld.

The three arms isolate distinct effects:

1. **All-frame fit:** all ten frames estimate frequency, and all are predicted.
2. **Support-only fit:** only frames accepted by the preceding past-only control
   envelope estimate frequency, but all frames still receive predictions. Their
   own training symbols estimate gains at the frozen block frequency.
3. **Support plus abstention:** use the same support-only frequency, but predict
   zero coherent mean on unsupported frames, giving those frames NMSE exactly one.

The source support decisions and thresholds remain unchanged from the
[frame-support assay](../2026_09_29_frame_support/README.md). No outcome selects
frames or changes membership. Frequency deltas are differences between models,
not errors against independent frequency truth.

This architecture is comparable in its noncoherent frame combination, but is
**not the deployed GLRT-64**: it uses different pilot symbols and profiles gains
per carrier rather than the production per-symbol correlation representation.
The result does not prove a production bug or certify an interchangeable detector.

## Evidence and reproduction

Four tests pass: recovery with independent frame phases, isolation from held
sample mutations, complete no-support fallback accounting, and exact identity
when all frames are supported. All 80 blocks complete in 2.2 seconds. The
summarizer checks input hashes, exact block membership, inherited support counts,
abstention accounting and same-support identity. Ruff lint/format pass.

```bash
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy --with matplotlib python -m unittest discover -s reports/2026_09_29_block_frequency_support -p 'test_*.py'
OPENBLAS_NUM_THREADS=1 timeout 120 uv run --no-project --with numpy --with scipy --with matplotlib python reports/2026_09_29_block_frequency_support/block.py
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy --with matplotlib python reports/2026_09_29_block_frequency_support/summarize.py
```

## Decision for the wider sub-km effort

This closes the immediate generated-sequence/frame-support branch at the research
prototype stage. It supplies better handling of unsupported observations but no
justification for rerunning the geographic panels with a new frequency estimator.
It does not rule out improvements on broader data, different observables or
longer sequence support; it does make further tuning of this small corpus a lower
priority than independent physical calibration and model-error diagnosis.

The investigation chain is:

- [Sequence estimator](../2026_09_29_sequence_estimator/README.md): initial short-fit gains disappear with a stronger pilot baseline.
- [Longer sequence support](../2026_09_29_sequence_long_support/README.md): small mixed gains and limited availability.
- [RX frequency transfer](../2026_09_29_rx_frequency_transfer/README.md): equal-weight fusion fails; large intermittent disagreements appear.
- [Peak tracking](../2026_09_29_frequency_peak_tracking/README.md): large unstable estimates coincide with weak pilot evidence.
- [Timing diagnostic](../2026_09_29_weak_frame_timing/README.md): bounded timing shifts do not restore the weak frames.
- [Frame support](../2026_09_29_frame_support/README.md): control-calibrated abstention avoids treating noise-like maxima as measurements.
- **This block comparison:** most of the frequency influence is already suppressed by noncoherent pooling.

Next prioritize a diagnostic that can distinguish receiver/RF common-mode bias
from candidate-orbit/association error using held observations and independent
constraints. Do not infer physical oscillator or orbit corrections from this
weak-frame result. Reliable short-window sub-km accuracy remains unachieved.
