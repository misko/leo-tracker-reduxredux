# Peak tracking: large jumps occur when pilot evidence collapses

**Do not promote this continuity estimator.** Searching more frequency peaks
does not improve held pilot prediction, and the frozen causal rule makes no
changes to the selected global peaks in evaluation. The main advance is a
diagnosis: the large, unstable estimates are associated with extremely weak
pilot evidence, not demonstrated oscillator jumps.

The [preceding RX-transfer report](../2026_09_29_rx_frequency_transfer/README.md)
found intermittent RX differences up to 177 kHz. Here all eight visits, both
receivers and 80 frames each were retained. Cached pre-correction pilot matrices
reproduce every one of the earlier 800 held own-RX errors to within 1e-10.
Parent raw-input and implementation hashes are verified; pilot-cache hashes
are now also bound in `results.json`.

## What changed in our understanding

| Visit | Global versus legacy estimates changing by >1 kHz | Those with low explained energy | Mean held NMSE gain |
|---|---:|---:|---:|
| DS7 S31 | 28/100 | 28/28 | −0.00046 |
| DS7 S32 | 16/100 | 16/16 | −0.00039 |
| Other six visits | 0/600 | — | Approximately zero |

Positive gain means smaller held prediction error. All 44 large changes occur
below the frozen 0.2 explained-energy threshold; representative peaks explain
only about 1–2% of the training pilot energy and have held NMSE near one.
Another maximum can be found, but that does not yield a useful frequency estimate.
These comparisons measure changes between estimators, not the count of all
RX-difference excursions or absolute Doppler errors.

Inspecting the complete frame sequences supplies a more specific clue:

- S31: both receivers have exactly the same 23 weak frames; all have relative
  frame index divisible by three.
- S32: both have the same 18 weak frames, again all at indices divisible by three.
- Not every third frame is weak, and these phase origins are relative to each
  excerpt, not a decoded absolute frame counter.
- S02 has one shared weak frame. Some other visits remain below the threshold
  throughout despite much stronger support than the near-noise DS7 frames.
  Therefore 0.2 is not a calibrated universal signal-presence threshold.

![Paired pilot evidence across frame slots](pilot-support.png)

The shared frame-slot pattern is consistent with intermittent signal support,
but does not establish transmitted blanking. Common demodulation/timing errors,
interference or other waveform behavior remain possible. It argues against
automatically interpreting every fitted frequency as a physical observation.
This concerns the research demodulator in these prototypes, not proof of the
same failure in production tracking or an explanation of all position error.

## Frozen experiment

The [protocol](PROTOCOL.md) predates execution. All arms train on symbols
22–221 and evaluate on 222–301. The legacy arm initializes from 22–121;
the global arm searches the full training interval with an 8192-point FFT,
retains six strongest separated candidates and refines each locally. Each
carrier has its own static complex gain. Frequencies are ambiguous modulo
the OFDM symbol rate; no absolute alias is resolved.

The causal arm applies a bounded penalty for departing from the previous
selected frequency. Low explained energy clears history, preventing a forced
continuation through these weak frames. A sufficiently stronger candidate can
overcome the penalty and represent a true transition. It chooses the same
frequency as the global arm on all 800 evaluation cases. No parameters were
retuned after observing this outcome; there is no continuity-model promotion.

Three tests pass: signed/near-wrap frequency recovery and held-data isolation;
transient peak preference versus a strong real jump; and low-evidence history
reset. The 1,280-frame replay completed in 4.3 seconds. All 800 inherited errors
reproduce, exact evaluation membership and source bindings pass the summarizer,
and Ruff lint/format pass. No raw collection, production change or geographic
optimization was performed.

```bash
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy --with matplotlib python -m unittest discover -s reports/2026_09_29_frequency_peak_tracking -p 'test_*.py'
OPENBLAS_NUM_THREADS=1 timeout 120 uv run --no-project --with numpy --with scipy --with matplotlib python reports/2026_09_29_frequency_peak_tracking/tracking.py
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy --with matplotlib python reports/2026_09_29_frequency_peak_tracking/summarize.py
```

## Next discriminating experiment

Test a frame-level signal-present/noise mixture before fitting clock dynamics:
use training pilots to estimate support, preserve unsupported frames as missing
frequency information, and validate both presence and waveform predictions on
held samples. Check modest timing offsets on the weak frame slots to distinguish
missed synchronization from absent predictable content. Do not simply discard
difficult observations and report improved error on the survivors. Keep this
diagnostic separate from any eventual geographic comparison.
