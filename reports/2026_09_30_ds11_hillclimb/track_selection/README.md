# Track selection evidence transfers across two earlier recordings

The frozen family2 detector-score selection model passes its separate-record
screen. This supports correcting the observation model's distinction between
raw detection and retained track presence. It does not establish a position gain
or a calibrated satellite missed-detection probability.

Train on 8,705 margin-passing unique projected candidates from training visits
of DS10 donor16; validate on all 11,912 qualifying candidates from donor17.
The label is membership in the existing baseline track export, reconstructed
through public projection and trajectory APIs with original settings. No
satellite identity labels, horizontal truth, or DS11 errors enter this model.
Each receiver/window has total weight one; repeated projected IDs are deduplicated.

| Separate-record metric | Receiver/RF baseline | Add detector exact/control scores |
|---|---:|---:|
| Weighted mean log probability | -0.599132 | -0.581716 |
| Mean gain over baseline | — | +0.017416 nats |
| Visits with positive gain | — | 1,385 / 1,943 (71.3%) |

The prespecified gates (>0.01 nats and >half of visits) both pass. This is one
recording pair at 5MS/s low setting; visits are temporally dependent, so the
visit win count is not a count of independent experiments. Detector scores are
statistics, not calibrated RF power. Higher exact score and lower control score
have the expected retention direction after conditional receiver/RF adjustment.

Both metadata exports finish within 22.15 seconds. Two component tests cover
window weighting, training-only standardization, analytic derivatives and stable
extreme log probabilities. All final fits satisfy the original optimizer-success,
gradient and finite-difference gates.

The initial `summary.json` remains failed: BFGS requested internal tolerance1e-7
and reported precision loss at gradient6.75e-6. `numerical_repair.py` repeats the
same zero-seed optimization with stopping tolerance1e-5, equal to the unchanged
protocol qualification threshold. No data, features, objective, ridge, or transfer
threshold changed. Detector-score coefficients are exactly identical; both fits
terminate successfully and the maximum derivative-audit discrepancy is1.57e-7.
The authoritative passing result is `qualified-summary.json`; the original
failure remains bound as evidence.

Next integration must preserve the distinction between P(track retained | raw
candidate observed and passed) estimated here and P(signal detected | satellite
geometry), which is not estimated here. In particular, this classifier cannot
assign a score to a physically undetected signal and must not turn missing
tracks into hard sky exclusions or inverse-probability weights for positions.
Use it to model the detection-to-track selection step in an explicit observation
model, with separate clutter and source-activity assumptions and a held-record
position gate. No production positioning default changes from this screen.
