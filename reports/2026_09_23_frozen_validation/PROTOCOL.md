# Frozen model comparison before validation evidence access

Evaluate exactly the 124 validation scans in the existing complete-inventory
split: Sep 22 08Z (44) and Sep 21 08Z (80). Keep groups separate. Within each,
evaluate nested 1/6/16/all views from Sacramento 250 km and Reno 500 km priors.
No training or final-test scans may enter the validation cohort. The final
64-scan TEST group remains closed. Existing historical production exposure is
not disproved by this prospective procedural separation.

## Seven fixed estimator configurations

1. Blind zero-epoch baseline using the published score, 100-to-0.1953125 km
   grid, three-candidate diverse beam, full retained causal catalogue.
2–4. Fixed baseline identities, one global epoch, scales 0.2/1/5 seconds.
5–7. Fixed baseline identities, one epoch per scan, scales 0.2/1/5 seconds.

Keep the original minimum 3 s span, occupied-second weights, 800 Hz capped loss,
randomized per-track masks, per-track training-profiled CFO, canonical RF,
causal TLE cutoff, candidate-generation policy, zero altitude, epoch ±5 s bounds
and helper stopping rules. Numerical source hashes are frozen in `freeze.json`.
Execution adapters may change only for input/output compatibility or diagnosed
bugs, with deviations disclosed; changing a scientific rule invalidates the
frozen comparison and requires preserving the earlier results.

No reassignment model is promoted into the selection set: its improvement
failed to replicate on the second TRAIN group. Satellite-specific epochs and
receiver drift likewise lack evidence of consistent localization improvement.
Pooled TRAIN location is not an initialization for validation. Validation
starts from the original prior grids. No true coordinate enters visibility,
candidate selection, fitting, initialization or optimization stopping.

Seal all baseline searches before scoring their complementary rows or reference
errors. Fit every timing arm from these sealed baseline locations and original
training-only identities. Seal every timing inference before held/reference
evaluation. Retain all exceptions and failures; do not drop difficult scans.

## Selection and reporting

Publish every group/view/prior/configuration, coordinates, location error,
held capped/uncapped frequency RMS, counts, runtime and solver diagnostics.
For selection, average starts within each group/view; average 6/16 views to
form the medium regime; weight short (1), medium and long (all) regimes equally,
and weight both groups equally. Select the configuration minimizing that mean
location error, using reference coordinates only after all inference is sealed.
Report worst group/start, every duration result, and whether any reaches 300 m.
The six correlated views/starts do not create additional independent groups.

A failed, nonfinite, out-of-prior, visibility-invalid or timing-boundary arm
makes a configuration ineligible. A timing fit that misses its declared stopping
rule is also ineligible. Report ineligible outcomes rather than replacing them.
The grid baseline has a fixed completed budget, not a stationarity claim.
If all configurations are ineligible, abstain from selecting a winner.
Configurations within 0.010 km of the lowest mean error are tied: prefer
baseline, then global, then per-scan; within a timing family prefer stronger
regularization (smaller scale). No per-duration tuning on two groups.

After selection, freeze the chosen complete rule before a single final-test
evaluation across all duration views. A test failure is a failure, not a prompt
to tune on TEST. Further development must use TRAIN and a new prospective test
cohort for new final claims. A single final group cannot establish broad field
reliability even if it passes. No RF collection or deployment is authorized by
this validation experiment.
