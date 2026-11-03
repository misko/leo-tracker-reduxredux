# Repeated-candidate influence diagnostic

Freeze before outcomes. Use all nine cached q020 eight-scan panels, unchanged
measurements, candidate banks, and training/held masks. Verify previous observed
Hessians and input bindings. Compute each track's full mixture score gradient
at the cached optimum. Assign a diagnostic group only when its training-MAP
candidate probability times signal responsibility is at least 0.5. Others
remain ungrouped, retain full weight, and contribute to all scores.

Group across the eight scans by candidate number, across RX/RF. Eligible groups
occur in at least two distinct recordings. Rank groups by norm of predicted
E/N movement for half weight: -0.5 H^-1 sum(group gradients), in metres.
Select the largest training-only influence, never using reference or held data.
The grouping remains fixed; candidate probabilities inside each track continue
to vary during fitting. This is a weighted composite likelihood diagnostic,
not a calibrated joint probability model or verified satellite identification.

Refit the full mixture with selected tracks at weight 0.5 and others at 1.
One local start from cached baseline, unchanged +/-12-km and +/-5-second
bounds, at most100 iterations/160 evaluations. Cap each panel at90seconds.
Qualify optimizer success, no boundary, projected gradient<=0.01 and
finite-difference gradient discrepancy<=0.02. Also fit weights0.99 and1.01
to audit the local predicted response; require relative error<=5% or
absolute E/N discrepancy<=0.5 m for the symmetric difference response.

Score with the unweighted original model on ALL held observations, and split
selected versus remaining tracks for diagnosis. Evaluate reference error only
after selection/fitting. Report all panels including failures, all group ranks,
and each group's per-recording contribution. A gain confined to the downweighted
tracks or the known geographic reference is insufficient for promotion.

## Coverage amendment before any refit

The first panel has zero favored candidate groups appearing in two scans,
and the runner stopped at the support assertion before fitting. Existing
catalogue recurrence evidence also distinguishes raw alternatives from favored
associations. Preserve cross-scan support counts, but test repeated-track
influence for groups with at least two tracks (including within one scan).
This tests candidate-group dominance; it cannot establish a cross-scan orbit
correction. Selection, weight, fit caps, and outcome audits remain unchanged.
