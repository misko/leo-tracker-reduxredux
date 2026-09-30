# Held-frame test of local carrier/time alignment

The first bounded tile experiment does not show a consistent benefit from
shifting early signal sections before comparing tracks. Stronger matches fitted
on one frame largely disappear on another frame. This is a useful constraint on
the alignment hypothesis, not evidence that the remaining symbols contain no data.
No additional message bits or field meanings were established.

## Data and method

The frozen DS7/DS8/DS9 census contains 312 pilot-qualified 10 MS/s tracks.
For each edge, select the strongest 24 by minimum held-pilot coherence, with at
most one track per session/visit/channel. Upper selections span 18 sessions
(DS7: 8, DS8: 1, DS9: 15); lower selections span 15 sessions (5, 5, 14).
This is a quality-selected subset, not all tracks or independent satellite passes.

Use the two previously reserved evaluation frames (indices 1 and 3); calibration
frames are not scored. Verify each input NPZ against its decode receipt SHA256.
Upper available carriers are 480–487; lower carriers are 536–543. All are
non-pilot. Compare the inner six carriers, leaving margins for a ±1 carrier shift.
The tested sections begin at OFDM symbol 4 (array index 2), with lengths 8, 16,
and 32 symbols. A ±2 OFDM-symbol search fits entirely within observed data;
there is no wraparound, extrapolation, or pilot insertion. Symbols 2–3 are not
included in the reference tile because they provide the search margin.

For each of the 276 unordered pairs per edge, subtract each tile's complex mean
and normalize its vector norm. Fit one of 15 time/carrier offsets by maximizing
complex correlation magnitude on evaluation frame 1. Fit a phase rotation there
as well. Freeze both for evaluation frame 3 and for its immediately adjacent,
nonoverlapping tile. Compare against zero offset with its own discovery-fitted
phase rotation. There are 48, 96, or 192 complex measurements per tile.
These are soft observations, not independently decoded bits.

Pair direction follows the fixed pilot-quality ordering. The resulting symmetric
pair table is a dissimilarity assay, not a single globally aligned embedding.
Average-linkage trees use sqrt(2−2r) on frozen held-frame scores. Four-cluster cuts
are an exploratory consistency diagnostic, not an inferred satellite count.
The adjacent tile uses the same frozen transform, without fitting it anew.
This tests local transfer; it is not yet an exhaustive sliding tessellation.

## Results

| Edge | Tile length | Fitted similarity | Held similarity | Gain over phase-only | Adjacent matrix Spearman | Adjacent four-cluster ARI |
|---|---:|---:|---:|---:|---:|---:|
| Upper | 8 | 0.254 | −0.004 | −0.005 | −0.001 | 0.024 |
| Upper | 16 | 0.186 | 0.007 | 0.005 | 0.113 | 0.024 |
| Upper | 32 | 0.134 | 0.001 | 0.004 | 0.015 | −0.051 |
| Lower | 8 | 0.263 | 0.013 | −0.006 | −0.029 | −0.014 |
| Lower | 16 | 0.184 | 0.006 | −0.004 | −0.034 | 0.025 |
| Lower | 32 | 0.132 | 0.003 | 0.005 | 0.033 | −0.035 |

Fitted similarity is a magnitude selected over 15 hypotheses; held similarity is
the real component after freezing discovery phase. Their scales have different
selection biases, so their difference is not itself a calibrated significance
test. The comparison against the held phase-only baseline is the relevant gain.
Pairs share tracks; no independence-based p-values are claimed.

As a check against frame-dependent common phase, also compare held correlation
magnitudes with the time/carrier offset still frozen. Mean gains are
−0.0044, −0.0031, −0.0037 on the upper edge and −0.0189, +0.0011, −0.0013 on
the lower edge. Corresponding adjacent-matrix correlations range from −0.062 to
0.071. Removing sensitivity to common phase does not reveal a consistent gain.

Eight selected tracks have conditional satellite labels, all different within
their edge group. There are **zero same-ID cross-session pairs** in this subset.
Consequently this experiment cannot assess satellite-specific repeatability.
The stored summary separately identifies same-session and different-session
pairs; shared-session effects must not be interpreted as identity.

![Upper-edge held-frame alignment](local/tile-alignment/upper.png)

![Lower-edge held-frame alignment](local/tile-alignment/lower.png)

## Interpretation and next discrimination

A single fixed local shift does not make these early soft patterns persist
reliably across frames in this subset. This is consistent with changing symbols,
frame-dependent pattern state, remaining calibration error, or insufficient
per-tile signal; it does not distinguish these explanations. Centering removes
constant tile bias. This differs from the earlier multi-frame phase-profile
clustering and does not invalidate evidence of simultaneous cross-receiver
agreement. Longer tiles also mix early unknown structure with known repetition.

The next discriminating experiment should fit shifts between simultaneous
receivers viewing the **same frame**, validate on separate symbol coordinates,
and then compare visits conditional on the known repeating-pattern state.
That separates failure to recover a transmitted pattern from actual changes
between frames. More unrestricted pairwise shift searches would not establish
new bits. A satellite-conditioned extension needs deliberate revisit selection,
rather than expecting repeated labels in a quality-ranked subset.

## Reproduction and artifacts

Run `tile_alignment.py` using NumPy, SciPy, and Matplotlib. It reads existing
decoded artifacts without collecting RF or modifying raw recordings. Input and
method SHA256 values, selected track metadata, metric summaries, all pair scores,
shift choices, and average-linkage arrays are saved under ignored
`local/tile-alignment/`. `summary.json` names each column of the NPZ `values`
array. No data are committed.

Three synthetic tests verify exact time/carrier/phase recovery and transfer,
the failure of a discovery search to create held-frame correlation from
independent noise, and adjusted-Rand label invariance.
