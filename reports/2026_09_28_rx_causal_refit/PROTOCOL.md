# Training-only refit under the causal frequency reference

The frozen-transfer study found a small tilt advantage over controls, but its
coefficients were optimized against a uniform frequency reference. This experiment
refits the same model family against the fixed causal reference to remove that
training/scoring mismatch. It does not change the causal predictor or nomination bank.

## Training isolation

Use six leave-one-calibration-record-out folds from the original geometry dataset
(12 lanes). Before constructing training features or causal histories, retain only
the other five recordings' reception windows. Exclude every held-frequency window,
the omitted recording and all original evaluation recordings from fitting.

Reuse each original fold's joint count distribution and feature scaler, which were
fitted using only those same five reception recordings. Verify their hash and
training membership. Within geometry centers columns 3:8 separately by lane,
nominee and receiver over reception forecasts. On the omitted recording, carry its
reception forecast mean into held windows as before; never recenter on held geometry.

The causal frequency predictor starts separately per lane and receiver, scores before
updates, ignores role labels and uses the frozen defaults from the preceding study.
Training histories contain reception only. The omitted-record scoring history runs
through reception into later observations without a boundary reset.

## Fits and controls

Keep sigma at 500 Hz, the fixed nomination priors and all existing likelihood terms.
Use the existing joint MAP fitter unchanged: D/E/S/T dimensions 3/4/6/8, prescribed
coefficient/nuisance priors, two starts per arm, original parameter bounds, exact
absent-model fallback, and the original optimizer stopping rules. D's nested seed
is the fixed neutral beta [-2,0,0], not a coefficient selected using omitted outcomes.
Refit beta, occupancy and persistence. E remains in the nested fitting ladder and
is reported as an elevation-only ablation; the primary comparisons remain T-D and T-S.

Score each omitted recording's reception and held roles using its newly fitted
D/E/S/T. Add T with swapped receiver geometry and reversed geometry, plus a
quarter-period frequency-shift control for each D/E/S/T arm. Every control shares
the same causal frequency reference and retains
its own presence-filter history. No causal-predictor tuning, widened persistence
bound, nomination refresh, or retrospective candidate selection is allowed.

Report per-record and equal-record role scores relative to the causal reference,
T-D, T-S, T-swapped, T-reversed, T-shifted, and full-score changes versus the completed
frozen-transfer D/S/T counterparts. Export fit starts/convergence, selected nulls,
parameter bounds, window populations and per-window scores/posteriors.

## Execution and evidence

Verify prior completed evidence before launch. Bind dataset, saved CV models,
frozen-transfer result, new source/tests, protocol and launcher hashes into an
experiment seal. Completed fold checkpoints must bind that seal, input and source
hashes and membership; exclusive writes only. A resume may reuse only an exactly
matching checkpoint. Preserve incomplete or failed receipts rather than overwriting.

Run one numerical thread, nice priority, 4 GiB and a 300-second total limit. No
multi-hour campaign, RF collection or QNAP mutation. Run component tests before the
real fit, audit training isolation and score arithmetic independently afterwards,
and preserve every optimizer receipt even if a start fails.

These recordings remain reused development evidence. Training-only refitting does
not make their later outcomes an untouched confirmation set. A model/control gain
is not proof of satellite identity, direction or sub-kilometre accuracy. Selection
of a subsequent confirmation cohort must use metadata alone and disclose earlier
research exposure.
