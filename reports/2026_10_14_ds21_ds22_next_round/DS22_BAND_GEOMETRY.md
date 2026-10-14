# DS22 sealed estimate geometry

Seven completed fitted-c matrices were inspected without reference coordinates,
held observations, predictors or optimizer calls. Distances below are Euclidean
kilometres in the original optimizer chart, not position errors. Halves share
discovery and initialization; these are not independent half pipelines.

| Case | B low–high separation | B all to half segment | C low–high separation | C all to half segment |
| --- | ---: | ---: | ---: | ---: |
| 001 | 2.941 | 2.804 | 21.859 | 7.147 |
| 003 | 4.232 | 0.053 | 3.862 | 1.050 |
| 017 | 3.866 | 1.285 | 2.309 | 1.618 |
| 019 | 12.084 | 71.353 | 11.383 | 61.740 |
| 029 | 6.221 | 0.326 | 6.776 | 0.110 |
| 031 | 2.179 | 1.535 | 4.423 | 2.030 |
| 033 | 1.536 | 0.233 | 3.847 | 0.352 |

019 is exceptional even without a reference: B combined lies 81.142/71.353 km
from its lower/upper estimates; C combined lies 61.740/73.120 km from its halves.
The halves agree with each other much more closely than either agrees with the
combined estimate. This motivates examining selected basins and candidate support,
but does not establish which estimate is correct or prove a particular defect.

001 also distinguishes the models: C's half estimates disagree by 21.859 km,
versus B's 2.941 km. Conversely, distance from the segment is not a valid error
proxy: B-031 is outside that segment while its configured-reference distance is
only 0.510 km. There is no requirement that a joint optimum lie between marginal
optima, and no position-selection rule is proposed from this diagnostic.

Source: `tools/ds22_band_geometry.py`, commit `df838ed3b`; two component tests
and Ruff passed. Exact protocol/terminal and source/archive bindings are in
`local/ds22-band-geometry-v1/report.json`. All seven matrices were sealed before
inspection; their protocol/terminal hashes were checked again after reading.
