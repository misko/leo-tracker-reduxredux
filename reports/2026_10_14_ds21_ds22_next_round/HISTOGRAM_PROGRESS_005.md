# Five paired DS21 development recordings

`histograms-runtime-004/histogram.png` compares the same five recordings:
001, 003, 005, 009 and 013. Both arms use CH1–8 with fitted c. Before is the
original discovery protocol; after is expanded discovery coverage. Later timing,
phase and candidate-bank experiments are excluded. This is 5 of 34 eligible
development cases, not full-dataset performance.

| Model | Paired before median km | Paired after median km |
| --- | ---: | ---: |
| A | 1.871189 | 2.180070 |
| B | 2.729078 | 2.021218 |
| C | 1.751815 | 2.387111 |

Coverage removes the catastrophic 013 solution, but the median improves only
for B in this paired subset. No model meets the 0.5 km median objective.
The new 003 C result is 5.214916 km versus its original 1.956673 km;
its conditional lower/upper errors are 5.944149/0.905251 km, so combined-view
regression remains material. Do not promote coverage as a general fix.

The collector validated five explicit runtime overrides against original
scientific parents and bound sealed outcomes before plotting. All other rows
come from the unchanged matched collector. The CSV has all 204 model/arm rows,
including pending cases; eight before and five after matrices are available.
`summary.json` statistics describe all available estimates per arm, whereas
the medians above and histogram use only the same five paired cases.

The latest 24-unit wave completed without orchestration failures in 141.172
seconds using ten workers. The two new matrices each contain 54 original-budget
calls, with no completed calls repeated. Plot, CSV, summary and source-bound
data are retained together in `histograms-runtime-004/`.
