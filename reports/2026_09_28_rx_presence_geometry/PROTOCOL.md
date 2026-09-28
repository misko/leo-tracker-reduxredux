# Explicit target-presence ablation

The prior model conflated omitted catalogue mass with the possibility that no nominated target is currently observable. A shortlist of probability mass one must not prohibit a target-absent state. This experiment tests that state assumption before any new emission-coefficient optimization. The original goal of validated geometry-assisted association remains open.

## Frozen inputs and scope

Use the immutable pilot model/dataset and four-record confirmation dataset. Refit no Doppler forecast, receiver mapping, alias, clutter intensity, signal width, geometry coefficient or feature transform. The calibration set is exclusively the six pilot recordings' reception windows. Pilot evaluation and confirmation outcomes are already reused research data; the following comparisons are exploratory, not blind tests.

All 1,356 calibration reception windows have at least one visible nominee. There is no certified target-free calibration population. The old Poisson/uniform-circle clutter model is retained as a reference assumption, not treated as learned physical clutter truth. An audit of count dispersion and frequency histograms must accompany interpretation.

## State model

State 0 means no nominated target; states 1..K nominate one frozen track/candidate. The absent state has the full paired clutter likelihood. A present state has the existing paired candidate-set likelihood, integrating shared RX noise and summing all raw candidate alternatives. Empty candidate sets remain observations.

Normalize the existing retained-candidate log priors across states 1..K, without probability floors; the old other-catalogue component is excluded from that conditional nomination distribution. Retained catalogue mass remains a reported support limitation. Presence is a separate probability pi, with initial state distribution v = [1-pi, pi*w_1, ..., pi*w_K].

Between windows separated by dt seconds, use the continuous-time refresh transition

`P(dt) = exp(-dt/tau) I + (1-exp(-dt/tau)) 1 v`.

The process retains its state between refreshes and redraws presence and nomination at a refresh. It permits disappearance and nomination changes without assuming a whole-block common target. It is a declared stochastic observation model, not an orbital handoff law. Use actual timestamp gaps; no reset at reception/held boundary. Score a held window before consuming it. Keep all calculations in log space, including tiny nomination priors.

## Calibration-only selection

For each frozen emission arm D, S and T, evaluate pi in {0, 0.01, 0.1, 0.5} and tau in {0.1, 1, 10} seconds on calibration reception only. Pi=0 has one canonical tau=1 choice and exactly equals the absent reference. Select the highest complete calibration log predictive density; exact ties prefer smaller pi then smaller tau. This finite, equally sized state-model selection is the only fit. The frozen emission coefficients are deliberately retained to isolate the state assumption; this is not a newly optimized full geometry model.

After selection, score all pilot evaluation and confirmation windows with the selected parameters and fixed feature transformations. Export reception and held presence posteriors separately from conditional nomination log weights. Report equal-record mean full log score per unique paired window, S-D and S-absent, T-S, and per-record signs.

## Controls and decisions

For T use receiver-axis swap and geometric trajectory reversal with its selected state parameters, without selection/refitting. For D/S/T shift every nominated frequency prediction by exactly one quarter of the lane alias period, retaining geometry, observations and prior weights. This fixed nomination control tests frequency alignment; never select a favorable shift. Recompute reception filtering and held prediction under every control.

An all-absent selection is an honest negative result. No-target probability must not be forced positive to manufacture associations. Evidence for an enhancement requires beating absence, geometry-free presence modelling, and nomination controls on held observations with unchanged denominators. A positive reused-panel result still needs further confirmation and a defensible background model before default promotion. Failure here does not exhaust joint emission/state models, because emission coefficients are held fixed.

## Execution

Test transition normalization/semigroup, arbitrary time gaps, zero-time identity, absence with full catalogue mass, tiny-prior recovery, score-before-update and brute-force small-state equivalence. Freeze source/input hashes before execution. One numerical thread, nice19, 4GiB, maximum300seconds for the complete finite-grid selection and scoring. No new RF, raw IQ or QNAP writes. Preserve failed runs and do not tune the grid after evaluation.
