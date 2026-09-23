# Model-limit review after fine spatial refinement

This is a read-only review of the frozen best-first scorer and the existing
grid-resolution experiment. It does not use a position reference and does not
claim that a selected location or satellite identity is correct.

## What the current score can and cannot resolve

The spatial grid is no longer the only material discretization. The scorer
evaluates exact TLE Doppler at each cell, but for every satellite it searches
only the eleven integer time shifts `-5, …, +5 s`. It chooses the shift with
minimum training RMS, after analytically fitting one constant frequency offset
on the same training rows. The reported per-track candidate is then chosen by
minimum randomized-evaluation RMS. Thus time shift and constant offset can
absorb part of the position-dependent Doppler change, while the evaluation
rows also participate in satellite identity and cell selection. The score is
useful for comparative search, but it is not independent predictive evidence.

The existing sensitivity receipt already shows that nuisance time refitting is
large enough to change the apparent spatial surface. At 50 km, its
frozen-identity synthetic p90 is 175.4 Hz when integer tau is refitted and 721.9 Hz
when the anchor tau is held fixed. At 12.5 km, measured residuals still have a
104.3 Hz median, 155.4 Hz p90, and 218.3 Hz maximum; only 81.25% of sampled
placements keep all ten frozen tracks below 200 Hz. These samples do not prove
a spatial bound, but they show that smaller cells alone cannot be assumed to
remove the residual floor.

The 34-track objective audit gives stronger evidence of non-spatial limits at
the selected 12.5 km cells. Six tracks select a tau boundary in each city, with
eight distinct tracks hitting a boundary in at least one of Sacramento or
Reno. Five of 34 tracks change NORAD between the two selected cells, while only
21 retain the same integer tau. Sacramento's largest single track contributes
about 62% of the reported capped loss and selects `tau=+5 s` with 840.7 Hz
held-out RMS; the corresponding Reno residual is about 828 Hz. Because both
values exceed the 800 Hz cap, this track raises the objective floor but is a
constant term locally and cannot steer the cell ranking unless its residual
crosses below the cap. The remaining unsaturated tracks, boundary-constrained
nuisance fits, and identity switches can still move the aggregate optimum as
the lattice is refined. The cap limits outlier influence but also hides
improvements above 800 Hz from the search ranking.

Constant-offset fitting removes the mean residual for each track. Position is
therefore informed only by within-track Doppler shape after projection away
from the constant vector. A location perturbation whose Doppler effect is
nearly constant across a short track is intrinsically weakly identified by
this score. The represented-one-second weights do not restore that lost
component. They also do not make tracks statistically independent.

## Recommended next experiment

Run one bounded, source-snapshotted local factorial experiment around each
already selected Sacramento and Reno cell. Use a fixed 25 km square and the
nested `12.5, 6.25, 3.125 km` lattices. Reuse exact propagated states, the same
fixed observation mask, every eligible three-second track, and the full causal
catalogue. Do not optimize against or report position truth.

For every local cell, preserve all candidate rows and compute these variants:

1. **Spatial baseline:** current integer tau grid and fitted training offset.
2. **Tau resolution:** exact Doppler at tau steps `1.0, 0.5, 0.25 s`, always
   choosing both candidate and tau from training rows over the full catalogue.
   Cross the step size with the domain: first hold `[-5,+5]` fixed to isolate
   quantization, then repeat at `[-7,+7]` to isolate boundary truncation. Do not
   silently convert a boundary hit into evidence for the cell.
3. **Offset projection:** for each fixed candidate and tau, record both the raw
   position-induced Doppler change and its demeaned training/evaluation shape.
   Report the fraction of spatial signal removed by the fitted constant. This
   measures position–offset confounding without pretending that zero receiver
   offset is physically known.
4. **Association:** compare full-catalogue identity selected by training RMS
   with the present evaluation-selected identity, and a frozen-identity result
   using the selected cell's training winner. Record top-two training gaps,
   evaluation gaps, switches across neighboring cells, and tau-boundary hits.

The decisive outputs are the minimum capped all-track objective at each spatial
and tau resolution, movement of the minimizing cell, per-track loss changes,
and identity/tau switch counts. Also report an evaluation score obtained after
training-only identity, tau, and offset selection. If `6.25→3.125 km` changes
the objective and selected cell negligibly while `1.0→0.25 s` changes them,
tau quantization dominates. If finer spatial grids help only before demeaning,
constant-offset confounding dominates. If identities switch with small
training gaps and materially change evaluation loss, association ambiguity
dominates. If none changes the result, the remaining floor is consistent with
orbit/model error or measurement noise, but this experiment alone cannot
separate those two.

This factorial comparison should precede another broad or finer grid search.
It directly tests the three current discretization and selection mechanisms at
the same locations and with the same observations, while avoiding a new
position fit or any use of reference coordinates.

## Evidence reviewed

- `tools/research/search_multiresolution_tle_coverage.py`, especially
  `score_prediction_bank` and `_track_best`.
- `tools/research/run_best_first_tle_search.py` and
  `tools/research/best_first_tle_search.py`.
- `reports/2026_09_23_grid_resolution_sensitivity/README.md`.
- `reports/2026_09_23_best_first_fine_resolution/objective-audit.json`.
- `reports/2026_09_23_best_first_tracking_search/README.md`.
