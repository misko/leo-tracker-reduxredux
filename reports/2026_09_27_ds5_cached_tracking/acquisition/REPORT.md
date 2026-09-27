# Acquisition variant results

Rank-seeded confirmation is not a viable replacement for blind coarse search.
The natural-stride seeded candidate costs 307.477 ms across 256 development
receiver-visits versus 597.565 ms for the packed baseline, a 1.943x server CPU
speedup. It retains only 8 of 36 baseline reference positives, loses 28, and
produces two unmatched candidate positives. Of the 28 losses, 12 seeded results
are fractionally incomplete, 15 are complete but fail the positive gate, and one
is positive at a different association. The fixed pilot controls retain 0/4 at
2.5 MS/s and 2/4 at 5 MS/s. There is no automatic fallback in this comparison.

Both unseeded FP32 FFT candidates preserve development decisions relative to the
stable packed FP64 V4 baseline:

| Candidate | Matched positives | Lost | Extras | Server CPU speedup | Remaining factor to 10x |
| --- | ---: | ---: | ---: | ---: | ---: |
| Built-in FP32 FFT, strided | 36/36 | 0 | 0 | 1.393x | 7.178x |
| FFTW FP32 FFT, strided | 36/36 | 0 | 0 | 1.505x | 6.644x |

Both FP32 variants retain all eight pilot receiver-controls across the two rates,
keep every noise and tone receiver-control negative, and have no control decision
changes. Neither changes rank order, selected window, projected epoch, or rank
score because the V4 ranker uses its separate rank FFT implementation.

The built-in FP32 candidate's maximum absolute drift over matched positives is
`3.06e-8` exact score, `8.06e-9` control score, `3.18e-8` margin,
`1.08e-4 Hz` CFO, and `1.85e-7` timing samples. The FFTW FP32 maxima are
`5.59e-8`, `8.66e-9`, `6.11e-8`, `4.07e-5 Hz`, and `8.09e-8` samples.
Across development and controls, the closest complete result remains 0.002284
from the strict 0.025 margin boundary, so the observed numerical drift is much
smaller than the nearest gate distance. This is development evidence, not a
general rounding guarantee.

The stable baseline library is independently fixed at SHA256
`8cdc21362e8cb98a21550b0ba2024674881ca106706d9c799b33e5d4f5a7e614`.
The FFTW receipt pins the actual server library
`/usr/lib/x86_64-linux-gnu/libfftw3f.so.3.6.10` at SHA256
`8fae0bc5d15b6caf5bb843f6a9328d2b08cd5440bef97722401cffdebc553611`.

Frozen receipts:

- `results.json`: seeded V4, SHA256
  `6e6934137b2a76e7e697c94eaeb6c6faf71a3fde94c43e894cbc3192e040c518`.
  Its exact runner is preserved as `run_seeded_acquisition.py`.
- `results_fft32.json`: built-in FP32, SHA256
  `2bebc5de8e419e3a98a547d08343a66e49a3c5f08e1da81271bf0bd8d87a1783`.
- `results_fft32_fftw.json`: FFTW FP32, SHA256
  `ce5474d2060a727c44bf9ec528b5d35d957544dd3d033a1d503e906c7a738c57`.

The packed detector is a comparison reference rather than physical truth, and a
miss is not a negative label. Development contains no established 5 MS/s real-IQ
reference positives. No holdout IQ or outcomes were opened.
