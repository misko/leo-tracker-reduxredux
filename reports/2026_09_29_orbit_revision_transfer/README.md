# A shared orbital-revision coefficient does not transfer usefully

**Keep the fresh baseline; do not launch a geographic refit with this correction.**
One common revision coefficient, learned from the other two datasets, stays near
zero and does not consistently improve held residuals on the excluded dataset.
The declared predictive gate failed, so the subsequent position-information
test was not launched. No sub-km improvement is established.

| Target DS | Donor DSs | Fitted coefficient | Changed cases | Improved / worsened | Median paired gain | Mean paired gain |
|---|---|---:|---:|---:|---:|---:|
| DS7 | DS8 + DS9 | −0.001630 | 1,337 | 612 / 725 | −0.03074 Hz | −0.02123 Hz |
| DS8 | DS7 + DS9 | −0.001435 | 1,277 | 626 / 647 | −0.00168 Hz | +0.04417 Hz |
| DS9 | DS7 + DS8 | −0.006790 | 794 | 398 / 396 | +0.00015 Hz | −1.75041 Hz |

Positive gain means lower held error. Four changed DS8 cases tie within 1e-6 Hz.
Across all 3,408 changed cases, 1,636 improve and 1,768 worsen; median gain is
−0.00969 Hz and mean gain −0.39959 Hz. These small mixed changes do not justify
adding the coefficient. The bounds were not active.

All 3,983 eligible cases remain in full-population results. Unchanged and missing
revision directions do not receive invented improvements. DS9 late has zero
changed cases; its changed-subset metrics are explicitly null. Every panel is
retained in `summary.json`. A summary initially emitted NaN for that empty subset;
the reporting code was corrected to explicit null without changing model results.

## Model and held-out dataset separation

The [protocol](PROTOCOL.md) preceded execution. Model frequency is
`baseline + beta * (older_orbit - baseline)` with `beta` bounded to [−1, 1].
Positive one is the older orbit; negative one extrapolates a full revision beyond
the fresh orbit; zero reproduces baseline. This is a statistical frequency-space
direction, not a dynamically propagated intermediate or future orbit.

Fit one beta using only the training observations of two datasets. Apply it to
the third dataset's held observations. Center both residual and revision direction
by each track's training mean; optimize Student-t4 loss at 100-Hz scale, averaging
observations within tracks, tracks within datasets and donor datasets equally.
Search 81 fixed coefficients including zero and endpoints, then refine every
interior grid-local minimum. Choose by donor training loss only. The protocol
does not claim mathematically certified global scalar optimality between grid
points. All scalar refinements report success.

Donor counts are 2,637 for the DS7 fold, 2,672 for DS8 and 2,657 for DS9. No target
dataset observation fits its coefficient. The inherited location and candidate
assignments were previously trained within each dataset, so these remain
conditional development comparisons, not independent site validation. Donors
can be later in time than targets; this is not a causal online estimator.

## Controls on all eligible target cases

| Dataset | Full older revision: mean gain | Full extrapolation: mean gain | Fitted coefficient: mean gain |
|---|---:|---:|---:|
| DS7 | −624.79 Hz | −618.45 Hz | −0.02108 Hz |
| DS8 | −452.90 Hz | −439.11 Hz | +0.04303 Hz |
| DS9 | −566.00 Hz | −566.38 Hz | −1.04813 Hz |

Both full-revision controls are substantially worse. Shrinking toward zero
avoids most of that degradation, but avoidance is not demonstrated improvement
over the existing baseline. There is no support here for extrapolating recent
GP revisions into a useful universal correction.

## Verification and provenance

The full revision vectors were re-exported through the same read-only archive
and propagation ports as the [exact orbital replay](../2026_09_29_orbit_revision_prediction/README.md).
Each vector reproduces the prior older-orbit held error, training slope and
training-centered RMS within 1e-6; maximum held-error discrepancy is 4.66e-10 Hz.
The eight missing older records get zero direction. Input hashes and element-line
digests are verified before reuse. `directions.json` retains all masks, residuals
and directions; `results.json` binds it and the fitting source/protocol and
retains each fold, coefficient and target score. No orbit provider bytes are
published by these exports.

Three tests pass: synthetic coefficient recovery/bound handling, isolation from
mutating all held residuals and directions, and constant-offset invariance.
Ruff lint and formatting pass. Each bounded stage uses one numerical thread and
returns within its 120-second cap. An export lint correction was followed by
re-export to bind final source. No RF, download, archive mutation, production edit,
position optimization or reference-coordinate selection occurred.

```bash
sudo -n env OPENBLAS_NUM_THREADS=1 timeout 120 /opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/bin/python reports/2026_09_29_orbit_revision_transfer/export.py > reports/2026_09_29_orbit_revision_transfer/directions.json
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python -m unittest discover -s reports/2026_09_29_orbit_revision_transfer -p 'test_*.py'
OPENBLAS_NUM_THREADS=1 timeout 120 uv run --no-project --with numpy --with scipy python reports/2026_09_29_orbit_revision_transfer/fit.py
.venv/bin/python reports/2026_09_29_orbit_revision_transfer/summarize.py
```

## Decision

The free candidate-slope model removed too much conditional position information;
the far more constrained shared revision coefficient now fails predictive
transfer. Neither should be promoted. Preserve the exact fresh orbital baseline
and the reproducible revision vectors for future independently constrained
models. More free orbit coefficients would require new evidence rather than
continued tuning of these exposed panels. Independent timing, receiver pose,
verified identity or precise orbital information remains a stronger direction
than a universal revision extrapolation. Reliable short-window sub-km accuracy
remains unresolved.
