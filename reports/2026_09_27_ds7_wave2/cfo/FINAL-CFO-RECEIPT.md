# Final DS7 Wave2 CFO receipt

This receipt supersedes the interpretations in `README.md`, `CORRECTION.md`,
and the four-window summary in `profile-results-v3.json`. It preserves every
earlier result and excluded row. The final eligible diagnostic uses visits 5
and 8 for real-data training and visit 11 for held waveform evaluation, on
channel 3 at 11.44 GHz within the same exported track for each receiver. Visit
12 remains explicitly inapplicable because it is channel 2 at 11.19 GHz.

The deterministic control applies a different seeded QPSK phase to every
even-Qin symbol row, equally across all eight tones. The profile model removes
one static complex gain per tone, so those symbol-varying phases cannot be
absorbed by its nuisance amplitudes. The identical held matrices, fixed
real-training predictions, and ordinary profiled-coherence objective are used
for real and scrambled values. No held or control value changes a prediction.

| receiver | method | state | boundary frames | real coherence | scrambled coherence | difference |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| 0 | baseline | supported | 0 | 0.13431 | 0.00678 | 0.12753 |
| 0 | ordinary profile | supported | 0 | 0.15063 | 0.00647 | 0.14416 |
| 0 | robust profile | supported | 0 | 0.15134 | 0.00645 | 0.14488 |
| 0 | differential phase | rejected | 4 | 0.02984 | 0.00688 | 0.02296 |
| 1 | baseline | supported | 0 | 0.10302 | 0.00713 | 0.09590 |
| 1 | ordinary profile | supported | 0 | 0.10410 | 0.00704 | 0.09707 |
| 1 | robust profile | supported | 0 | 0.10459 | 0.00706 | 0.09753 |
| 1 | differential phase | rejected | 8 | 0.02673 | 0.00647 | 0.02025 |

The differential estimator reaches the frozen ±2 kHz boundary on 4/14 and
8/14 held frames, so it is rejected despite its retained diagnostic scores.
Ordinary and robust estimators expose no boundary frames. Their explicit
100 Hz coarse step, 5 Hz fine step, and robust four-iteration limit equal the
installed defaults and are now bound at the call site. Every fixed prediction
remains inside the ±2 kHz acquisition basin.

This is one held visit per receiver and one deterministic scramble. It closes
the missing-control accounting row but is not calibrated false-positive
performance, frequency truth, accuracy, precision, population evidence, or a
geographic result. No extractor or downstream method is promoted.

The final control read used 9,600,000 bytes and 6.82 measured analyzer seconds.
Wave2 cumulative use is 163,200,000 bytes and 27.22 seconds, within the original
512 MiB and 120 second leases. No RF was collected and no pose, score, or
reference value was accessed.

## Frozen files

- Spec v4 SHA-256: `3fd20b5215f8cc81aa95f66008c50b35359c7c5786da8d21f1ee5ec255e1f767`
- Runner SHA-256: `3cae536f3041ffb5ac6064347e308ec026935ee39b7f1430af3f6395c9844ab9`
- Result SHA-256: `5930e255a4192ad188d6baf58b76436ccabc44ce236060fae201678e44496bea`
- Reference audit: `reference_excluded`
