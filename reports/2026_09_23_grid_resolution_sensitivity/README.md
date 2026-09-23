# Grid-resolution sensitivity receipt

`result.json` is a source-snapshotted, fixed-candidate geometry experiment for
the Sacramento fine beam-32 finalist at `(-81.25, -81.25)` km. It freezes the
ten recorded finalist NORAD identities and their anchor taus, then moves only
the observer position. It never accesses truth data and does not establish
that the frozen identities or location are correct.

The 32 paired samples per row are deterministic uniform phases in a square
cell, `U[-s/2,s/2]^2`. Edges and corners are listed separately in the JSON and
are not included in the percentiles. The model baseline is the frozen
candidate's anchor-tau prediction. At every displaced position, the constant
frequency offset is fitted on the fixed randomized training partition only.
The main model column permits the normal `[-5,+5]` second tau fit; the receipt
also records the stricter fixed-recorded-tau result. Exact geometry with no
above-horizon tau/observation is excluded from success and recorded as
nonfinite. This visibility diagnostic is not a claim of parity with the
searcher's coarse eligibility gate.

| Cell spacing (km) | Model tau-refit median / p90 / max Hz | Model <200 Hz track samples | All 10 tracks <200 Hz | Measured median / p90 / max Hz | Measured <200 Hz track samples | All 10 tracks <200 Hz |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 12.5 | 44.2 / 100.9 / 147.2 | 100.00% | 100.00% | 104.3 / 155.4 / 218.3 | 98.13% | 81.25% |
| 25 | 61.0 / 112.3 / 252.6 | 98.75% | 87.50% | 112.8 / 172.7 / 315.6 | 95.31% | 65.62% |
| 50 | 80.3 / 175.4 / 530.1 | 91.88% | 43.75% | 121.3 / 216.7 / 501.6 | 86.56% | 37.50% |
| 100 | 127.5 / 593.9 / 1231.0 | 65.94% | 21.88% | 155.7 / 603.1 / 1279.3 | 57.50% | 15.62% |
| 200 | 457.7 / 1929.1 / 3121.9 | 32.81% | 12.50% | 455.3 / 1938.6 / 3107.3 | 31.25% | 9.38% |
| 400 | 1752.6 / 5358.2 / 9322.4 | 8.44% | 0.00% | 1806.6 / 5403.5 / 9377.7 | 8.13% | 0.00% |

Under a pooled 90th-percentile `<200 Hz` criterion, 25 km is the largest
tested spacing for the measured residuals. A simultaneous all-ten-track
criterion is stricter: even at 25 km it survives only 65.62% of the sampled
cell phases, and 12.5 km survives 81.25%. Sample maxima are observations, not
certified spatial bounds. The recorded fixed-anchor-tau model is deliberately
more severe than the tau-refit model (at 50 km its p90 is 721.9 Hz versus
175.4 Hz), showing that nuisance tau refitting materially changes the local
surface.

For this recording, use 25 km when seeking at least 95% pooled track-trial
survival under a strict 200 Hz cutoff. A 50 km search is a faster discovery
stage, but should retain several candidate regions and refine them before
rejecting a location. At 100--200 km, a fixed 200 Hz center-point gate rejects
many otherwise matching hypotheses. A future coarse search should account for
the range of predictions within the cell, rather than treating its center as
the only possible receiver position. These are empirical choices for these
ten hypotheses; 32 sampled placements do not certify a maximum cell size.

Reproduce the calculation against the same read-only corpus with:

```bash
sudo -n env OPENBLAS_NUM_THREADS=1 PYTHONPATH=src:. .venv/bin/python \
  reports/2026_09_23_grid_resolution_sensitivity/source/measure_grid_resolution_sensitivity.py \
  --evidence /home/mouse9911/.cache/leo-research/cf510316-prior-comparison-v1/evidence \
  --anchor-finalists reports/2026_09_23_grid_resolution_sensitivity/anchor-finalists.json.gz \
  --output reports/2026_09_23_grid_resolution_sensitivity_reproduced
```

`result.json` contains hashes before and after computation for the sensitivity
tool, fast search engine, loader, frozen kernel, and copied anchor. The
top-level `manifest.json` hashes the receipt artifacts.
The exact matching computation sources are preserved in `source/`.

Recreate the figures and independently check the reported percentiles and
survival fractions against the saved raw samples, without accessing the corpus:

```bash
.venv/bin/python reports/2026_09_23_grid_resolution_sensitivity/render.py
```
