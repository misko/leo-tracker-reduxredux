# DS7–DS9 coverage for header decoding

This is a frozen-manifest audit, not a new RF collection or a check of current
raw-IQ retention. All three datasets remain in scope for decoding work.

| Sample rate | DS7 recordings | DS8 recordings | DS9 recordings | Combined |
|---|---:|---:|---:|---:|
| 2.5 MS/s | 19 | 20 | 20 | 59 |
| 5 MS/s | 27 | 17 | 12 | 56 |
| 7.5 MS/s | 23 | 15 | 20 | 58 |
| 10 MS/s | 19 | 13 | 53 | 85 |
| Total | 88 | 65 | 105 | 258 |

There are no duplicate session IDs or source-manifest hashes among these
members. Every capture's recorded bandwidth equals its sample rate in these
manifests. Hashes, counts, and calculations are saved in ignored
`local/ds789_header_coverage.json`.

The existing demodulator uses subcarrier spacing 240 MHz / 1024 = 234,375 Hz.
An ideal contiguous interval of bandwidth B can contain at most
`floor(B / 234375) + 1` carrier centers: 11, 22, 33, and 43 at the four rates.
These are optimistic bounds, before pilot removal and filter rolloff. The
existing edge-recovery helper selects 24 data carriers around eight pilots;
that extraction is narrower than the ideal 10-MHz bound.

Under the specific hypothesis of one BPSK bit per carrier and a 114-symbol
codeword placed contiguously within one OFDM symbol, the first and last carrier
centers span at least `(114 - 1) * 234375 = 26,484,375 Hz`. Thus none of the
DS7–DS9 captures contains that whole codeword in a single instantaneous band.
Adding disjoint recordings does not create simultaneous wider bandwidth, and
revisiting the same satellite does not establish that its header repeats.

This does **not** rule out partial decoding, repeated/interleaved codewords,
time-spread allocations, or combining independently verified repetitions.
It explains why the full-band UT recording remains useful for establishing
mapping and coding first. The 85 recordings at 10 MS/s are the widest available
DS pool for independent fragment checks once a candidate has a defined carrier
map. Selecting actual visits also requires signal-quality and raw-availability
checks; this audit does not claim those have been performed for DS9.

Sources are the immutable membership manifests:

* `reports/2026_09_27_ds7_post_ds6/manifest.json`
* `reports/2026_09_28_ds8_post_ds7/manifest.json`
* `reports/2026_09_28_ds9_post_ds8/manifest.json`

Spacing and selected-carrier evidence are in
`reports/2026_09_27_ds7_header/analyze.py` and `recover.py`.
