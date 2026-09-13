# Radio .20: saved-IQ repetition and acquisition coverage

Offline analysis finds intermittent stronger proposals in the saved 60-MS/s
CH3 capture that its six live scans missed. It does not establish a missed
valid acquisition. Recent 30-MS/s visits have much weaker frame-period
repetition, close to the saved control. No new RF was collected, and no
runtime gate or firmware changed.

## Spectral and repetition comparison

All inputs are the exported 2.5-MS/s complex IQ, independently hash-checked
against the capture receipts or frozen replay input. The analysis uses
4,096-sample Hann-windowed spectra (610.3515625-Hz bins), averaged in
131,072-sample blocks. Each incomplete final analysis block is explicitly
excluded. Parseval energy checks pass; a generated tone has unit normalized
lag correlation and zero input gives zero.

The repetition statistic is squared normalized complex correlation at a
10,000-sample lag: 4 ms, or three nominal 750-Hz frames. Nearby 9,000- and
11,000-sample lags provide descriptive comparisons. It is not a calibrated
detector, false-alarm test or RF identity measurement.

| Saved input | Median 4-ms lag power | Ratio to mean of nearby-lag medians |
| --- | ---: | ---: |
| 30-MS/s CH1–CH4 visits | 0.0000072–0.0000079 | 1.16–1.22 |
| 60-MS/s CH3 visit | 0.0000550 | 8.77 |
| 60-MS/s CH4 visit | 0.0000092 | 1.42 |
| Saved positive replay input | 0.0001491 | 18.95 |
| Saved control replay input | 0.0000082 | 1.90 |

The normalized spectral shapes are broadly similar; spectral flatness ranges
from 0.792 to 0.819. These are different recordings, not a controlled 30-versus-
60-MS/s experiment. The result cannot attribute the difference to sample rate,
antenna pointing, LNB power or a particular transmitter. The control is a
development input, not independently established ground-truth noise.

The [spectral/repetition figure](figures/2026_09_13_radio20_saved_iq_coverage/saved-visit-spectra-v2.svg)
and [numeric results](figures/2026_09_13_radio20_saved_iq_coverage/saved-visit-spectra-v2.json)
retain the per-input quantities and excluded tails.

## Replaying acquisition windows

The unchanged C coarse scanner was compiled for host replay. Its eight
proposals were ranked with the same full-pilot FFT power calculation, using
an independent NumPy FFT. All 18 original windows across the three replayed
physical visits reproduce their complete integer grids exactly and reproduce
their retained ranking scores within numerical tolerance.

| Input | Replayed windows | Maximum full-pilot rank power |
| --- | ---: | ---: |
| 60-MS/s CH3, six original live windows | 6 | 0.00389 |
| 60-MS/s CH3, spaced coverage plus originals | 54 | 0.02590 |
| 60-MS/s CH3, consecutive 14,000-sample windows plus originals | 1,803 | 0.03987 |
| 30-MS/s CH3, spaced coverage plus originals | 54 | 0.00550 |
| 30-MS/s CH4, spaced coverage plus originals | 54 | 0.00518 |
| Saved positive, spaced windows | 48 | 0.08503 |
| Saved control, spaced windows | 48 | 0.00475 |

The denser 60-MS/s replay takes 44.1 seconds on the host, including its two
controls. Its strongest proposal is at capture offset 6.4344 seconds, in a
window the live scanner did not examine. Stronger proposals also occur in
other seconds; this is not solely an event after the live worker finished.
Consecutive input windows do not enumerate every possible full-pilot start:
the unchanged scanner still selects only eight coarse proposals per window.

Rank power alone does not prove the repeated-pilot support, fresh handoff or
native feedback required for tracking. The replay therefore qualifies no new
acquisition. It shows that sparse scan timing can hide stronger proposals and
motivates evaluating temporal coverage and proposal selection on this retained
capture before changing the ARM scan policy. It supplies no justification for
lowering native or startup acceptance gates. The newer 30-MS/s CH3/CH4 windows
remain much closer to the control even with wider temporal coverage.

The [spaced replay](figures/2026_09_13_radio20_saved_iq_coverage/saved-visit-coverage-v1.json)
and [dense replay](figures/2026_09_13_radio20_saved_iq_coverage/saved-visit-dense-coverage-v1.json)
include all window offsets, scores, source/input/reference hashes and runtime.
Analysis sources accompany them. The physical state remains the
[last verified 30-MS/s CH4-upper visit](2026_09_13_radio20_clean_loss_visits.md),
TX disabled, serial `1040005e0b100007100010000bf33a5d4d`. Sustained tracking and
physical clean-loss continuation remain unfinished.
