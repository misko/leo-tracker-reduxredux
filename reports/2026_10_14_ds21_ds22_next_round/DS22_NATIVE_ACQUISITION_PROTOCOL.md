# Acquisition-conditioned native clutter: prospective qualification and control

DS22-109 and DS22-131 retain both complete forward-origin native-band states,
including the strict repaired 131 low-origin endpoint. No source is selected by
position error. The proposed single beta changes clutter log odds by beta times
the selected observation's standardized log fractional acquisition margin.
Positive beta increases clutter odds. Bounds are ±2, Gaussian prior sigma1,
optimizer scale .5; all existing satellite, band, calibration and timing priors
remain unchanged. There is no fitted intercept or receiver/band-specific beta.

The public TrackingCandidate fractional_margin is copied through
project_scanner_candidates to the exact selected candidate and observation.
It equals fractional_exact_score minus fractional_control_score; it is not a
probability. Qualification binds every row to that public candidate, its window,
frequency, receiver/channel/time, source manifests and passing gate. No maximum
over alternatives, margin-based filtering, missing-row substitution or redraw
is allowed. All selected margins must be positive and finite.

Randomized whole20s folds use seed20261014 and the existing immutable helper.
For each fold, log margins use only that training fold's mean and population SD;
zero variance fails. The transform is then fixed on both folds, without clipping.
This density conditions on a detector statistic from the same acquisition and
potentially shared waveform evidence. Selection/collider effects remain possible;
it is not independent evidence or a generative detector-set probability.

Qualification first: two source-bound units, each42 objective calls and no fits,
120s internal/135s TERM/140s KILL. Checks include public identity, both fold
transforms, exact beta0 objective/old gradients/posteriors, own-fold arm nesting,
nonzero beta and deterministic physical/q directional derivatives. Every failed
qualification remains recorded. Recursive imported sources, contracts, projection,
fractional scoring and tests are frozen before actual preparation.

After qualification only, the authorized control is16 fixed-geography calls:
2cases ×2origins ×2folds ×2arms (beta fixed0 versus learned). Both arms use the
same new wrapper, original native bank/frame/domain, complete original nuisance
seed and beta0. Each call has60s including5s independent audit reserve and600
actual evaluations, with strict original KKT unchanged. No free-position fits,
no retries, and all16 outcomes seal before opposite-fold predictions. Report all
unavailable pairs; separate direct density substitution from changed-parameter
predictive effects. No reference or original held/locked set is needed.

Both new arms predict native orbits once per evaluation; the historical band
wrapper predicted twice. Each band's new density has two cheap density passes
(baseline validation plus shifted score), with no additional orbit predictions.
This is a matched new-arm comparison, not a runtime comparison to historical fits.
