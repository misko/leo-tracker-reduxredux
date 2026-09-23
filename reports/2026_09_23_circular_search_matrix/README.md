# Circular prior search matrix

This experiment replaces the former 5,000 km square acquisitions with circles
declared before scoring: 350 km around Sacramento, 750 km around Reno, and
2,500 km around Denver. Both acquisition and continuous refinement remain
inside each circle. The single-scan cohort has 39 tracks and 1,415 uncapped
observations; quarter8 has 198 tracks and 5,890 uncapped observations.

All six refinements converged using nominal exact SGP4 states from the original
regional-orbit scorer. This matrix does not use the newer joint causal-orbit
model. The reference coordinate was opened only afterward to produce
`matrix.json` and `matrix.png`.
The five-block split trains blocks 0/2/4 and holds out 1/3; it measures
within-span shape interpolation rather than future prediction.

The results remain composite scores with uncertain identities. Agreement across
the three centres demonstrates repeatability inside these particular declared
circles, not calibrated global confidence. The large positive boundary distances
show that none of the final estimates was held on a circular edge.

The earlier chronological 60/40 trial in the cache is preserved but excluded:
it used a different partition and cannot isolate the effect of changing the
search support. The published matrix uses only `*-fiveblock-*-v2` artifacts.

The report copies the six five-block-v2 acquisition receipts and compact
acquisition results, declared circle points, refinement results, circle
receipts, and qualification receipts into `inputs/`. The `source/` directory
freezes every numerical or orchestration source named by those receipts.
`qualify.py` checks their actual digests, cohort counts (39 tracks and 1,415
observations for single; 198 tracks and 5,890 observations for quarter8),
nonempty converged fits, and both acquisition and refinement circle boundaries
before evaluation truth is read.

Run from the repository root:

```bash
OPENBLAS_NUM_THREADS=1 .venv/bin/python reports/2026_09_23_circular_search_matrix/render.py
```

The command reads only report-local files, regenerates `matrix.json` and
`matrix.png`, and writes `artifact-manifest.json` covering every report file.
No mutable research-cache path is required. The first chronological trial is
not copied or evaluated.
