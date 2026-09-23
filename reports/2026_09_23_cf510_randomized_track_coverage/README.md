# CF510 randomized-track regional coverage

This report maps, on 50 km grids around Sacramento, Reno, and Denver, how many
of the declared ten longest tracks among 21 eligible trajectories from
`scan-fw-cf510316ae7f05d5` have at least one catalogue candidate with strictly
less than 800 Hz randomized-evaluation held-out RMS. Each map shows the full
0–10 count field and labels the five cells selected by descending count, then
ascending clipped best-RMS sum, east offset, and north offset.

The top-five tables in `summary.json` and `top-five-cells.csv` report each cell's count, coordinates,
clipped best-RMS tie metric, and the minimum-RMS candidate NORAD for every
qualifying track. The copied gzip inventories retain every qualifying
cell/track/candidate row, including NORAD, nuisance time offset, training RMS,
and held-out RMS.

`top-cell-track-support.png` complements the maps with top-five count bars and
three city panels, each a ten-track by fifteen-cell best-RMS heatmap. Blank heatmap cells
mean that track has no catalogue candidate below the strict threshold at that
location. Map titles report how many cells share the maximum count.

`threshold-sensitivity.png` recomputes, without refitting, the maximum number
of observations belonging to tracks whose best candidate is below 800, 500,
300, 200, or 100 Hz, together with the number of cells attaining each maximum.
These are whole-track observation totals: every observation in a qualifying
track receives weight in the count. They are not pointwise inlier counts. The
machine summary also records the all-ten-track minimax cell, chosen by the
smallest worst per-track best RMS.

## Interpretation

The observation partition is deterministic but observer dependent, so the
training and randomized-evaluation masks can differ between grid cells. The
same observations contribute across nearby cells and tracks can choose
different candidate IDs. These are exploratory held-out-selection coverage
maps, not independent validation, calibrated identity confidence, calibrated
position confidence, or position truth. Broad support at one cell means that
many tracks individually have some candidate below the declared threshold; it
does not establish a common joint satellite association or a position fix.

The underlying reconstruction produced 28 tracklets; 21 met the declared
length and support-span eligibility rule, and the longest ten were selected.
Their 372 observation IDs are unique in the kernel inventory. Two trajectories
can still overlap in underlying IQ support, so this does not establish
independent observations or duplicated samples. The standard support-centre
span is also about 18 ms shorter than an earlier full-support-extent export;
this report uses the frozen standard kernel inventory throughout.

No reference coordinate or labelled satellite identity is used for scoring,
cell ranking, threshold sensitivity, or minimax selection. After those outputs
are fixed, the renderer reads a copied evaluation-only coordinate and reports
great-circle distance for interpretation; it verifies and ranks every grid
before opening that file. Candidate
survival is conditional on the exact causal catalogue snapshot, visibility
screen, nuisance-offset grid, randomized partition, and strict 800 Hz rule
implemented by the frozen pipeline.

## Reproduction

Run from the repository root:

```bash
OPENBLAS_NUM_THREADS=1 .venv/bin/python reports/2026_09_23_cf510_randomized_track_coverage/render.py
```

The renderer reads the three copied losslessly compressed JSON results, NPZ maps, and compressed candidate
inventories under `inputs/`, verifies their cross-file bindings and selection
ordering, regenerates `coverage-maps.png` and `summary.json`, and writes the
artifact manifest. The numerical pipeline used to produce the frozen grids is
copied under `source/`; rendering does not read mutable cache state. A full
numerical rerun still requires the original public stored-track source and
causal TLE archive state. Those large authorities are digest-bound by the
copied results rather than duplicated in this compact report.
