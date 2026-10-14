# Seven paired DS21 development recordings

`histograms-runtime-005/histogram.png` adds 011 and 025 to the same-case
comparison, now 001, 003, 005, 009, 011, 013, 025: 7/34 eligible recordings.
Both arms use CH1–8 and fitted c; before/after refers only to original versus
expanded discovery coverage, excluding subsequent physics prototypes.

| Model | Paired before median km | Paired after median km |
| --- | ---: | ---: |
| A | 2.491943 | 2.180070 |
| B | 2.729078 | 2.021218 |
| C | 1.595252 | 2.387111 |

The changed membership means these medians must not be interpreted as a new
algorithmic improvement relative to the previous five-pair summary. On the
same seven cases A/B improve modestly and C worsens. No model meets 0.5 km.
025 is a new material regression: expanded-coverage A6.049037 and C4.458743 km,
versus original A3.297411 and C1.121626 km (rounded). C's two conditional halves
are 2.726496/2.910571 km, both better than its combined fit. Conversely 011 C
combined0.813596 km beats its conditional halves8.890072/3.918383 km.

All eight explicit runtime overrides passed the unchanged collector's original
protocol, fitted-c budget and sealed-receipt checks. The CSV retains all204
model/arm rows, including pending cases; nine before and seven after matrices
are currently available. Histogram and paired medians use only the same seven
cases; summary.json's per-arm statistics use all available estimates.
