# Periodic counter hypotheses: ambiguity and corrected ties

The existing power-of-two counter screen remains negative after an independent
recalculation and a training-only tie sensitivity check. This is an audit of a
frozen hypothesis bank, not another blind scan or a newly decoded field.

## Inputs and falsifier

Use the three existing DS10-F010 paired excerpts v1085, v1150 and v1162.
Each NPZ hash is checked against both the original within-visit receipt and its
paired extraction receipt. RX0 earlier qualified frames select coordinates and
models; RX1 later frames evaluate. The candidate bank remains periods
2/4/8/16/32/64, every phase and both polarities, evaluated at the original
physical frame indices, including gaps. No new coordinate or period is added.

A literal counter-bit interpretation predicts that discovery-fitted periodic
signs improve over a frozen discovery-majority sign on later frames and exceed
coordinate-maximum circular controls. Firmware still supplies no such mapping:
the audited TX sequence operation is a bitmap OR, and software/patent sequence
fields are not demonstrated RF coordinate counters.

## Why audit ties?

The historical implementation selected the first best-fitting model. Several
models can agree on training accuracy yet disagree on unseen frame predictions.
The sensitivity assay averages predictions across every tied bank entry using
only training scores. Its accuracy is expected agreement under that mixture;
it does not choose a model or threshold using evaluation data. Duplicate bank
entries retain their original weights, so this is not a uniform prior over
distinct physical hypotheses.

| Excerpt | Tested coordinates | Ambiguous held predictions | Original maximum gain | Mixture maximum gain | Original corrected-tie rank | Mixture rank |
|---|---:|---:|---:|---:|---:|---:|
| v1085 | 119 | 69 | .34783 | .34783 | .78261 | .73913 |
| v1150 | 134 | 79 | .66667 | .66667 | .77778 | .88889 |
| v1162 | 149 | 90 | .72727 | .68182 | .36364 | .45455 |

Gain is accuracy minus the frozen constant predictor, maximized over tested
coordinates. Each rank includes zero rotation and the maximum across all
coordinates at every held-frame rotation. Bonferroni over both methods and
three excerpts gives **1 for all six assays**. Large selected gains are therefore
unsurprising under these controls.

The original per-coordinate gains and strict floating-comparison ranks reproduce.
For v1150, the old rank .66667 omitted a mathematically tied score due to floating
roundoff; counting equality within 1e-12 raises it to .77778. The old artifact
is preserved, and the revised ledger explicitly records the correction.

These excerpts share a session and conditional candidate; they are not independent
satellite passes. Circular rotation preserves held coordinate dependencies but
does not preserve the physical timing of qualification gaps. Resolution is coarse
(23, 9 and 11 held frames), and the data have been reused. The result rejects
support for this particular direct periodic-bit model; it does not rule out a
counter behind unknown FEC, scrambling, interleaving or event-driven updates.

## Reproduction

```sh
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy python reports/2026_09_29_firmware_cluster_reaudit/counter_ties.py
```

Ignored `local/counter-ties.json` includes every coordinate, original physical
frame index, tied-model count, gain and cyclic maximum. Tests cover ambiguous
training fits, physical-frame gaps and floating-point ties. No RF collection,
fixture modification or public-IQ analysis occurs.
