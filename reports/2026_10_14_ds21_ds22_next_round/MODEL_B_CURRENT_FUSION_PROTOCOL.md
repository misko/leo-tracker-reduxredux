# Current coverage B035/B029 fusion diagnostic

The current after/coverage cohort makes035 and029 the largest B errors. This
training-only diagnostic uses their original cached-v2 all/low/high winners and
each case's exact original after bank. It does not compare objective values
across different before/after banks, select candidates or replace source results.
The independent bank/proposal inventory is owned by the parallel A investigation.

The code requires actual `GroupCalibrationObjective` wrapping
`hard60_joint_clock.JointClockObjective`, the original Hard60 Gaussian likelihood
port, common smooth receiver clocks and constant receiver/group contrasts. It
rejects C or alternative likelihood/clock models. Three saved own-view objectives
and NLLs replay, and timing/clock/group prior penalties close separately.

Each view's correction is frozen with the existing `freeze_group_calibration`
port in its original time/RF/group frame. The two original frozen functions are
evaluated on precisely the same matched observation timestamps, RFs, receiver IDs
and channels. Coefficients are not copied between centering frames. Exact window
identity and candidate-column alignment are required; half observations must
partition the full observations. No fitted parameter state is transported.

For each half the diagnostic compares four prediction arrays:

- All geography/timing orbit plus all frozen correction.
- Half geography/timing orbit plus all frozen correction.
- All geography/timing orbit plus half frozen correction.
- Half geography/timing orbit plus half frozen correction.

The first pair of baseline band NLLs must sum to the original full NLL. Each final
own-half combination must close its original half NLL. Satellite-plus-clutter TV,
MAP switches, confidence and mass use the existing assignment comparison port.
Orbit changes jointly include geography and satellite common/relative timing,
so they cannot isolate geography alone. Hybrid likelihoods are prediction-space
diagnostics, not calibrated-model evidence, accepted fitted states, or model
selection scores. Original physical priors are reported separately.

Report physical correction differences on shared windows, separated into original
baseline, receiver/RF affine, common clock and group offset functions; also report
relative timing differences and candidate occupancy. At the original full fit,
compute the exact likelihood derivative in each missing receiver-band drift
direction, `group_design * (time - training_center)`. A zero-centered added drift
prior has derivative zero there. A nonzero score establishes only a local training
direction; it cannot establish accuracy or justify a fit by itself.

Top hypotheses are (1) incompatible band calibration/residual trends induce
assignment switches under the shared clock model, or (2) geometry/timing and
association modes differ despite calibration. Candidate/proposal loss is a
separate strong common-pipeline hypothesis, investigated in parallel. If the
matched evidence favors a missing drift direction, a next narrow prototype could
add only receiver-band drift with the existing explicit prior and original
training-only starts/budgets. That requires a concrete reviewed protocol; this
operation fits nothing.

Fresh namespace `local/model-b-current-fusion-v1`; source authority freezes before
preparation. Parents in order are `model-a-pipeline-coverage-035-cached-v2` and
`model-a-pipeline-coverage-029-cached-v2`, under next_round/local. All bindings are
rechecked after preparation and before sealing. Whole-operation bounds include
preparation: internal180 seconds, external TERM195, KILL200. The successful
two-case operation performs six full objective calls, six extra orbit calls and
22 extra likelihood calls, zero optimizers, no held or reference usage. Frozen
function extraction and cache preparation still perform numerical work.
