# Changing header signs in existing DS7–DS9 recordings

The first six candidate header symbols contain changing real-sign observations
that reproduce across receivers in six cached visits. This is evidence for a
shared changing signal; it is not yet a decoded MAC header or verified plaintext.
No satellite ID, timing, orbit, length, CRC, or FEC field is established by this test.

## Data and method

`local_header_recovery.py` reads nine existing paired DS7/DS8 visit caches and
two DS9 visit caches. This is a bounded cached subset, not an exhaustive analysis
of the three datasets. No new recording or download was needed.

Only frames in both receivers' native decoder evaluation sets are eligible.
Both receivers must have held-pilot coherence above 0.5. Five caches have no
eligible paired frames; the six qualifying caches are listed below. Carrier
coordinates are aligned by the intersection of native FFT bins, not array index.

Within each visit, the first half of eligible frames selects positions and
confidence thresholds; the remaining frames evaluate them. Selection uses RX0
alone. Each symbol/carrier coordinate must have 20–80% positive real signs in
discovery. This excludes apparently constant positions, although noise can also
make a coordinate appear variable. Each coordinate's discovery median of
`abs(real(z))/abs(z)` supplies a frozen confidence threshold. Evaluation samples
are selected using RX0 confidence alone, without looking at RX1 agreement.

The measurement covers OFDM symbols 2–7 after the existing template-relative
calibration. All nonzero cyclic shifts of the evaluation RX1 frame sequence
provide mismatched-frame controls at identical symbol/carrier coordinates.
These shifts are dependent descriptive comparisons, not independent trials or
a formal significance test. Per-coordinate marginal sign baselines are also
recorded in the detailed result.

## Results

| Cached visit | Eligible frames | Changing coordinates selected | Evaluation decisions | Matched agreement | Mean mismatched agreement |
|---|---:|---:|---:|---:|---:|
| S01 | 44 | 41 | 474 | 80.17% | 55.06% |
| S02 | 41 | 45 | 439 | 76.77% | 51.90% |
| S13 | 20 | 129 | 655 | 69.47% | 54.27% |
| S22 | 32 | 113 | 918 | 76.80% | 51.15% |
| S23 | 42 | 103 | 1,071 | 78.71% | 55.27% |
| DS9-middle | 45 | 95 | 1,099 | 86.35% | 52.49% |

S06, S07, S18, S19, and DS9-first have no eligible paired frames under this gate.
In DS9-middle, symbol 3 has 90.54% agreement over 148 selected decisions;
symbols 4–7 have 82.38–88.17%. This is descriptive, not a selection of the
best symbol followed by an independent validation.

Agreement is not transmitter bit accuracy: both receivers can share distortion,
an incorrect model, or interference. Nor does agreement prove that the signal
is unencrypted. The result does establish that treating every changing header
observation as independent receiver noise would discard reproducible structure.
The 13.65% disagreement in the strongest visit makes exact parity searches
fragile; a coding search should preserve soft evidence and uncertain positions.

## Raw observations and reproducibility

The ignored `local/local_header_recovery.json` stores source SHA-256 hashes,
discovery/evaluation frame numbers, carrier coordinates, per-symbol statistics,
and both receivers' raw sign strings. Nonnegative real sign is represented as
`1`. It also stores the selection mask and an agreement-only string: `?` means
excluded or disagreeing. An agreed sign is still an unverified observation.
These strings have not been descrambled into MAC bits or checked by a CRC.

Run with NumPy:

```sh
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy python reports/2026_09_28_sequence_semantics/local_header_recovery.py
```

The companion tests check rejection of fixed coordinates, recovery of injected
shared changing signs against frame-shift controls, and empty/constant baselines.
Tests and Ruff checks pass. Raw observations remain under the ignored `local/`
directory. Next, use these reproducible changing positions to evaluate a soft
coding hypothesis with held-out frames; no field meanings should be assigned
until a mapping survives that evaluation.
