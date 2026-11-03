# Small timing shifts do not recover the weak pilot frames

**No tested timing correction recovers a useful pilot measurement in the selected
weak slots.** Their held correlation remains near wrong-template controls, while
nearby strong frames retain clear pilot evidence. Total raw power is also lower
in the weak slots on both receivers. This favors treating these slots as lacking
a usable pilot-derived frequency observation rather than assigning them a large
physical frequency jump. It does not prove transmitter blanking or complete
absence of RF content.

This follows the [frequency-peak study](../2026_09_29_frequency_peak_tracking/README.md).
S31 and S32 are two visits from the same DS7 recording, so their agreement is not
independent replication across sites or sessions.

## Held results

Each cell is a median over four selected frames. The correct pilot timing trial
was chosen using earlier training symbols only; later symbols supplied these
coherences. Wrong templates were allowed their own training-only frequency fit.

| Visit / RX | Weak: selected timing coherence | Weak: wrong-template coherence | Strong: selected timing coherence | Weak/strong raw power |
|---|---:|---:|---:|---:|
| S31 / RX0 | 0.025 | 0.039 | 0.582 | 0.645 |
| S31 / RX1 | 0.034 | 0.045 | 0.493 | 0.720 |
| S32 / RX0 | 0.031 | 0.033 | 0.512 | 0.711 |
| S32 / RX1 | 0.032 | 0.024 | 0.525 | 0.728 |

Weak-frame normalized complex prediction error remains above one: selected-timing
group medians 1.0215–1.0322, versus original-timing medians 1.0176–1.0247.
All four groups worsen after timing selection. Maximizing a weak training
correlation did not yield predictive improvement. Strong-frame errors remain
roughly 0.693–0.777, with selected shifts at zero or one half native sample.

Raw power ratios compare total power in the same central frame interval, not
calibrated desired-signal power or SNR. The weak frames contain substantial
received energy; loss of the specific predictable pilot is the supported claim.
Different emitters, interference and common processing effects remain possible.

## Frozen method and limits

The [protocol](PROTOCOL.md) predates this run. Frame selection uses the previous
report: for each RX/visit, the first four training-period frames below 0.03
explained energy and first four above 0.2. This is a targeted posthoc diagnostic,
not representative or prospectively blind sampling. There are 32 receiver-frame
cases in total, including 16 weak and 16 strong controls.

Original digest-verified raw IQ is re-demodulated over 25 timing trials: shifts
of −2 through +2 OFDM symbols, combined with −1, −0.5, 0, +0.5 or +1 native
sample. At 7.5 MS/s the maximum excursion is about 8.93 microseconds. Pilots
22–121 choose the shift and fit frequency/static carrier gains; pilots 222–301
evaluate. The 17-symbol-rolled template receives the chosen timing and its own
training fit. It does not receive a separate 25-trial timing search.

The search does not exclude larger timing errors, sample-clock stretch, alternate
pilot/frame formats, or overlapping sources. The matching every-third-frame
pattern in the preceding report still needs independent physical attribution.
No GPS timestamp, satellite ID or range measurement has been decoded.

## Verification and next step

Two synthetic tests pass: known frequency and held prediction recovery, and
proof that mutating held samples cannot select timing or change fitted gains.
All 800 timing trials completed in 19.4 seconds. The summarizer independently
checks 32-frame membership, 25 trials per case, training-only maximum selection
and all source hashes. Ruff lint/format pass. No new RF, production changes or
geographic fit was performed.

```bash
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy --with matplotlib python -m unittest discover -s reports/2026_09_29_weak_frame_timing -p 'test_*.py'
OPENBLAS_NUM_THREADS=1 timeout 120 uv run --no-project --with numpy --with scipy --with matplotlib python reports/2026_09_29_weak_frame_timing/diagnostic.py
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy --with matplotlib python reports/2026_09_29_weak_frame_timing/summarize.py
```

The next useful estimator should represent signal support per frame and avoid
treating an unsupported frequency maximum as a measured Doppler. Validate a
signal/noise mixture or abstention rule on held pilots, report lost coverage,
and retain all missing slots explicitly. Only after that should a corrected
observation stream be compared in the frozen geographic panels. These waveform
diagnostics do not yet establish a sub-km improvement.
