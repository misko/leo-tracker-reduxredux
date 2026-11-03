# Paired RX frequency transfer exposes intermittent large disagreements

**Equal-weight frequency fusion is not ready for promotion.** A past-only RX
offset makes the estimates comparable, but averaging them does not reliably
improve held waveform prediction. More importantly, two visits contain large
intermittent frequency disagreements hidden by otherwise small median residuals.
Continuity-aware frequency hypotheses are the next concrete diagnostic target.

Eight existing DS7/DS8/DS9 visits, two receivers and 80 frames per receiver
produce 1,280 raw-IQ frame demodulations. The first 30 paired frames estimate
one offset; the next 50 supply 800 receiver-frame evaluations. No satellite
identity, orbit or true receiver position enters the fit.

## Results

| Dataset / visit | Training-qualified | RX1−RX0 offset (Hz) | Training difference MAD (Hz) | Held median absolute residual (Hz) | Held pairs above 1 kHz / 50 |
|---|---|---:|---:|---:|---:|
| DS7 S02 | Yes | 683,393 | 18.6 | 43.0 | 0 |
| DS7 S31 | Yes | 685,492 | 38.6 | 47.7 | 13 |
| DS7 S32 | Yes | 685,386 | 50.5 | 25.6 | 11 |
| DS8 S13 | Yes | 664,596 | 21.8 | 33.1 | 0 |
| DS8 S28 | No | 677,453 | 28.0 | 47.0 | 0 |
| DS8 S29 | No | 677,510 | 22.9 | 47.5 | 0 |
| DS9 middle | Yes | 685,690 | 29.3 | 11.2 | 0 |
| DS9 first | No | 683,492 | 30.5 | 32.4 | 0 |

Offsets are in the reconstructed within-visit frequency convention, combining
cached acquisition CFO and the newly fitted residual. They are not calibrated
LNB oscillator offsets: hardware, signal association and acquisition aliases
are not separated. Differences between visits must not be interpreted as
measured oscillator drift without those controls.

The >1 kHz count is a **posthoc descriptive diagnostic**, added after inspecting
the traces; it does not exclude observations or change the frozen qualification.
S31 and S32 reach approximately 146 kHz and 177 kHz absolute held residuals.
Their training intervals already contain 8/30 and 7/30 >1 kHz excursions. The
median-coherence/MAD qualification passes despite this intermittent behavior;
it is plainly insufficient to certify stable matched tracking. S02 has one
large training excursion but none in evaluation. All cases remain in the results.

![Receiver difference traces](rx-differences.png)

| Population | Blend improves held-pilot error | RX/visit groups with positive median paired gain |
|---|---:|---:|
| All inputs | 391/800 | 9/16 |
| Training-qualified visits | 236/500 | 5/10 |

No robust fusion gain follows. These correlated samples are not independent
trials. An RX difference becoming smaller after subtracting its fitted offset
is not itself an accuracy improvement. The held complex pilot prediction is
the independent evaluation target here; no absolute Doppler truth is available.

## Method and controls

The [protocol](PROTOCOL.md) preceded execution. Each original cached raw
excerpt's digest is checked, and the existing numerical demodulator is reused
without its later soft-symbol corrections. Both RXs must have matching sample
rates/edges and acquisition frame origins within 0.1 ms; all eight satisfy this.
This does not independently verify the same emitter or absence of frame slips.

For each frame, pilots 22–121 initialize frequency and pilots 22–221 fit a
frequency-only model with a static complex gain per carrier. Pilots 222–301
are withheld from parameter fitting. The first 30 frames estimate the median
RX1-minus-RX0 offset; it is frozen for the next 50.

Evaluate four frequency predictions while fitting target-RX gains only on its
training symbols: own-RX, 50/50 own plus offset-corrected contemporaneous peer,
50/50 without the offset, and a control rotating peer evaluation frames by 13.
The latter is an offline diagnostic, not a causal estimator. The zero-offset
blend deliberately combines incompatible frequency origins as a negative control.
All arm scores and all per-frame frequencies are retained in `results.json`.

Qualification uses only median initialization coherence >0.5 on both RXs and
training difference MAD <100 Hz. It is diagnostic, not an outcome filter.
Cached acquisition itself used the original observation, so the whole pipeline
is acquisition-assisted rather than prospectively independent end to end.

## Verification and reproduce

Three focused tests pass for signed offset transfer on a common trajectory,
isolation of the early offset from later mutations, and robustness to one early
outlier. An initial research-module import-path error was corrected before
execution. All 1,280 frame demodulations and 800 evaluation rows complete in
35.2 seconds without replacement or retry. The summarizer independently checks
all source hashes, exact membership and offsets. Ruff lint/format pass.

Intermediate pilot matrices remain ignored under `local/`. Original IQ and
production code are unchanged. No new collection or geographic optimization.

```bash
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy --with matplotlib python -m unittest discover -s reports/2026_09_29_rx_frequency_transfer -p 'test_*.py'
OPENBLAS_NUM_THREADS=1 timeout 120 uv run --no-project --with numpy --with scipy --with matplotlib python reports/2026_09_29_rx_frequency_transfer/transfer.py
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy --with matplotlib python reports/2026_09_29_rx_frequency_transfer/summarize.py
```

## Next scientific decision

Keep the existing position estimator unchanged. Test whether retaining multiple
pilot-frequency peaks and selecting them with a past-only continuity model
improves the independently held pilot predictions in the excursion cases.
Include wrong-track and interruption controls; do not smooth genuine transitions
away merely to obtain plausible Doppler. This will distinguish a tracking
failure from a need for more flexible physical clock modeling. Unequal receiver
noise and overlapping emitters remain alternative explanations.
