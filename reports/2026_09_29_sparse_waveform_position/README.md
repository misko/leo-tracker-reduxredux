# Sparse direct waveform corrections: matched geographic evaluation

The available direct waveform corrections produced **no consistent geographic
improvement**. Four of nine panels improved, five worsened, and the sub-kilometer
count remained2/9. Maximum position movement was17.71m. Keep the cached baseline.

| Dataset | Cached median error m | Corrected median error m | Improved panels | Sub-km cached → corrected |
|---|---:|---:|---:|---:|
| DS7 | 2023.56 | 2024.27 | 1/3 | 0 → 0 |
| DS8 | 1721.07 | 1722.84 | 2/3 | 0 → 0 |
| DS9 | 876.13 | 875.81 | 1/3 | 2 → 2 |

Errors use the inherited, previously exposed **unsurveyed reference**. These are
conditional research-panel results, not independently verified accuracy claims.

![Matched geographic outcomes](comparison.png)

## What changed

Applied all72 training-visit long-pilot residuals from the frozen four-visit
waveform experiment: four observations on each of18 tracks, eight corrections
per eight-scan panel. Each native residual was converted to canonical frequency
as `delta_hz * 11.2e9 / actual_rf_hz` and added to the existing dealiased value.
The deployed alias assignment was preserved and integer alias mapping verified.
No correction was extrapolated to another visit. No uncertainty weighting,
quality filter, candidate replacement or track selection was introduced.

Every held observation stayed byte-for-byte numerically unchanged. Both arms
retained the same4,328 tracks, candidate banks, times, masks and timing bounds
over72 recordings. There are198,806 observations, of which119,673 are training.
The72 modified values cover **0.0602% of training observations**, on18/4,328 tracks
(0.416%). This deliberately sparse coverage is a major limit: absence of improvement
here cannot establish that complete direct waveform re-estimation would fail.

## Fit and held-evidence checks

Cached and corrected arms each ran three identical starting points, selecting
by training score under the unchanged q020 unassociated-trend model. There were
53 qualified starts out of54. One cached DS7-late start returned an abnormal
optimizer status and was retained as unqualified; another start qualified.
All18 selected fits passed the independent gradient audit; maximum discrepancy
was0.0000821, below the frozen0.02 tolerance. Maximum selected projected gradient
was0.000625, below0.01. Original training scores and every held-track score were
replayed before fitting to within1e-7.

Held log scores improved in4/9 panels, using identical held measurements and
each arm's own training-derived posterior. An additional diagnostic evaluates
the original model at each corrected location/timing vector, holding the full
measurement model fixed; this also improves in4/9. These tests separate changed
training evidence from the geometric movement. See [TABLE.md](TABLE.md) for
every panel, geographic movement and both held-score differences.

The largest movement was DS9 early:17.71m, with error worsening639.50→657.02m.
DS9 middle, whose waveform prediction had shown a large gain in earlier
research, moved1.03m and improved reference error by only0.32m. Waveform prediction
improvement is not by itself a reliable indicator of geographic benefit.

## Relation to the alias audit

The preceding [alias audit](../2026_09_29_waveform_alias_audit/README.md) found
that research cross-visit regressions had omitted alias unwrapping. Operational
localization already uses dealiased canonical observations. This geographic
experiment uses those existing observations directly and adds only independently
fitted small residual corrections. It does not install the flawed wrapped-CFO
trajectory regression or claim an operational alias bug.

The corrected cross-visit replay is mixed: two-point refinement helps13/18 tracks,
but four-point refinement worsens pooled prediction error. The original two
reports now identify their old cross-visit conclusions as superseded. Their raw
artifacts remain available for audit.

## Decision and next evidence needed

Do not promote this sparse correction or frame-jackknife weighting. Before
expanding IQ processing, measure which training observations can actually affect
position in the retained-bank model. A bounded, training-only selection based
on position sensitivity would provide a more informative correction budget than
the earliest visits used here. Any follow-up must retain fixed candidates and
matched held observations, and report coverage rather than imply a full-dataset
reprocessing. Do not change RF collection or launch a long campaign on the basis
of these results.

Full reliable sub-kilometer accuracy remains unresolved. This experiment is a
local optimization around existing exposed solutions; it neither certifies a
global optimum nor supplies new geographic truth.

## Reproduction and evidence

- [PROTOCOL.md](PROTOCOL.md): frozen correction and fit rules.
- [summary.json](summary.json), [TABLE.md](TABLE.md): complete outcomes, coverage and hashes.
- `DS7_early_8.json` through `DS9_late_8.json`: applied corrections, all starts,
  selected fits, gradient audits and input/code hashes.
- [receipts.json](receipts.json): exit status for every bounded invocation.
- `run.py`, `launch.py`, `summarize.py`, `test_run.py`: fitting, orchestration,
  reporting, and projected-gradient boundary tests.

All nine commands exited0; total panel execution205.78seconds, maximum27.37seconds,
each below the60-second cap. Two boundary-gradient tests pass; two mapping tests
pass in the linked alias audit. Source artifacts, manifests, original observation
exports and result hashes are checked. Original persisted dataset/candidate
contracts were not rewritten: corrected arrays exist only in memory during the
research fit. No new RF was collected and no production analyzer was changed.
The reports and evidence are local; this turn did not publish to remote main.
