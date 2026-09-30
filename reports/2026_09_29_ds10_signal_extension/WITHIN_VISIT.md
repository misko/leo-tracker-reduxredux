# Repeated observations within a visit

We have successive frames and simultaneous independent receiver observations within
the same recorded visit. Three existing DS10-F010 excerpts each cover 120 ms and
contain 89 recovered frames per receiver. The nominal frame interval is 1/750 s
(1.333 ms). These are observations of a continuously tracked signal; the associated
NORAD 63400 satellite candidate remains conditional, not an identity decoded from RF.

## Changing early signs

We compared all held-out frames against all other held-out frames, always using
RX0 for the row and RX1 for the column. Coordinates are fixed: nonpilot carriers,
OFDM symbols 2–7. The first half of jointly qualified frames selects variable
coordinates and confidence thresholds using RX0 alone. The second half supplies
the comparisons. Each row's RX0-only mask stays fixed for every comparison.
This avoids selecting coordinates because the receivers agree.

| Visit | Jointly qualified frames | Held-out frames | Variable coordinates | Same frame agreement | Different frame agreement |
|---|---:|---:|---:|---:|---:|
| DS10-F010-v1085 | 45 | 23 | 119 | 80.2% | 59.2% |
| DS10-F010-v1150 | 18 | 9 | 134 | 78.4% | 58.7% |
| DS10-F010-v1162 | 21 | 11 | 149 | 75.6% | 58.6% |

The same-frame scores use 1,395, 631 and 828 selected sign decisions respectively.
Different-frame comparisons contain 506, 72 and 110 directed frame pairs, with
many reused decisions; these are not independent trials. Their pooled means
reproduce the previous all-cyclic-mismatch controls. The new matrix resolves
those controls into individual frame pairs.

The per-coordinate sign-bias baselines are 61.2%, 63.0% and 61.4%, respectively.
Consequently, 59% cross-frame agreement is not evidence that 59% of an unknown
message repeats. The strong diagonal excess supports frame-specific recoverable
structure. It does not establish a payload format, transmitter bit-error rate,
or a meaning for individual signs. Shared receiver distortion remains possible.

![All held-out frame pairs](local/within-visit/early-frame-agreement.png)

Rows and columns show physical frame indices, with irregular gaps caused by
calibration and quality selection. The color is sign agreement, not complex
correlation. Row-specific masks make the matrix asymmetric. There is no phase,
carrier or timing-shift search. The output also records comparisons at each
physical frame lag; lag in milliseconds is the index difference divided by 750
and multiplied by 1,000. No period or timing field is claimed from these lags.

## Repetition associated with the known T-code state

We separately classified states using symbols 194–225 and compared disjoint
earlier regions. This assay uses all jointly qualified state-classified frames,
not just the header's held-out subset. For each unordered pair of different
frames, the statistic averages the two cross-receiver complex correlations,
after centering each flattened region. These values are correlations, not bit
agreement percentages.

| Visit | Region (OFDM symbols) | Same-state correlation | Different-state correlation |
|---|---|---:|---:|
| v1085 | 2–7 | 0.161 | 0.135 |
| v1085 | 8–33 | 0.321 | 0.046 |
| v1085 | 34–129 | 0.340 | 0.059 |
| v1085 | 130–193 | 0.339 | 0.084 |
| v1162 | 2–7 | 0.140 | 0.079 |
| v1162 | 8–33 | 0.202 | 0.029 |
| v1162 | 34–129 | 0.240 | 0.048 |
| v1162 | 130–193 | 0.268 | 0.055 |

v1085 supplies 158 same-state and 338 different-state pairs from 32 classified
frames; v1162 supplies 8 and 47 pairs from 11 frames. v1150 has six classified
frames with distinct states, so it cannot support a same-state comparison.
These descriptive comparisons have dependent pairs and possible temporal/SNR
confounding; they are not significance tests or proof of new information.

The later regions repeat much more strongly with the known state. The earliest
region shows substantially less state dependence. We should therefore combine
the receivers within each frame for early information, and test state-conditioned
combining across frames for later structure. A held-out receiver/frame test is
needed before claiming that combining recovers additional bits. Blind averaging
across all frames would mix different states and changing early signs.

## Reproducibility

`within_visit.py` reads the existing paired caches and verifies their SHA-256
against the original summaries. It writes `local/within-visit/summary.json`,
per-visit NPZ files containing frame indices, match counts, decision counts and
selection masks, and the figure above. The JSON binds source summaries and the
analysis script by digest. All generated files remain Git-ignored. No recordings
were collected and no existing dataset manifests were changed.

Run with NumPy and Matplotlib installed:

```sh
python reports/2026_09_29_ds10_signal_extension/within_visit.py
python -m pytest -q reports/2026_09_29_ds10_signal_extension/test_within_visit.py
```

Two synthetic tests verify changing-frame discrimination and frozen comparison
masks, including the absence of diagonal excess for an entirely constant signal.
