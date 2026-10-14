# Model B: simple band weighting cannot rescue the tested alternative states

The unchanged B likelihood was evaluated separately on CH1–4 and CH5–8 at each
sealed final state from the anchor-profile experiment. The band terms reproduce
the original all-band likelihood to the 1e-7 replay tolerance. No calibration,
position, satellite assignment or timing was refitted; there was no held or
reference access in this diagnostic.

| Case | Final anchor | Low-band NLL | High-band NLL | Low clutter mass | High clutter mass |
|---|---|---:|---:|---:|---:|
| 039 | all, selected | 20983.190 | 13534.313 | 582.54 | 321.75 |
| 039 | low | 21158.716 | 14354.482 | 605.67 | 522.61 |
| 039 | high | 23077.601 | 14991.998 | 1087.31 | 680.07 |
| 023 | all, selected | 15687.108 | 12823.714 | 335.70 | 304.45 |
| 023 | low | 17403.194 | 14532.767 | 746.82 | 684.93 |
| 023 | high | 16889.401 | 13832.691 | 611.50 | 542.43 |

Lower NLL is better. The original all-anchor state scores better on **both bands**
than every alternative in this experiment. In particular, the previously
evaluated 023 high-anchor state has 1.279603 km error versus 5.599817 km for the
selected state, yet loses 1202.293 NLL on the low band and 1008.976 on the high
band. It is not being rejected solely because one band overwhelms a preference
for it in the other band.

Any nonnegative band-likelihood weights, with at least one positive, preserve
this likelihood ordering at these fixed states. If their sum stays at two,
even the smallest possible weighted likelihood gap exceeds the alternative's
prior advantage in every row, so the complete objective ordering also stays
unchanged. This is not a claim about refitting a reweighted objective: that could
produce different states. Nor does it establish satellite identity truth.

The original state also labels less evidence as clutter in both bands. These
are summed conditional clutter probabilities, not independently verified false
detections. A useful next investigation is whether independent-window mixture
assignments reward incompatible satellite explanations across time, or whether
another residual-model/calibration error drives the ranking. The current test
rules out a simple rescoring fix for the particular profiled alternatives.

Both training-only diagnostics used the genuine original B preparation and
candidate order. Each made three objective replays, three orbit predictions and
six band likelihood evaluations, with zero optimizer calls. Whole times were
31.308 s (039) and 22.659 s (023), under 180/195/200-second bounds during ongoing
parallel work. Sources and original sealed experiment inputs were bound before
preparation and checked afterward. Raw receipts are
`local/model-b-band-score-{039,023}-v1`.

The component test checks exact likelihood partitioning against a real synthetic
group-calibration objective and rejection of a changed sealed objective. It and
Ruff passed. This is additional root-cause evidence, not improved position
performance; the full DS21/DS22 target remains unmet.
