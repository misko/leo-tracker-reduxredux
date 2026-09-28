# Joint model prototype: findings and next decision

Completed a bounded offline experiment on 07:00 (clean control), 08:10 and 10:30 (large Reno errors). No RF collection, geographic search, production changes, cross-location proposals or external writes. Four numerical tests pass.

## Main result

At both 100 and 200 Hz block-noise settings, the joint model ranks the fixed sites:

- 07:00: known location, Reno estimate, Sacramento estimate.
- 08:10: Sacramento estimate (5.8 km error), known location, Reno estimate (675.8 km error).
- 10:30: known location, Sacramento estimate (18.3 km error), Reno estimate (688.0 km error).

Thus both large-error Reno locations are disfavored relative to the known location. However, the identical-likelihood frozen-ID/timing-marginalized control already does that. Joint reassignment lowers predictive NLL substantially while **reducing** known-versus-Reno discrimination. It is not a demonstrated location-accuracy improvement.

At the 100 Hz setting, reference-minus-Reno score gaps (negative favors known location) change from -1.1041 to -0.0387 at 07:00, from -4.2067 to -0.5011 at 08:10, and from -1.5539 to -0.6415 at 10:30 when moving from frozen IDs/no clock to joint assignments/clock. These scores are composite predictive NLL per evaluation block, not RMS or calibrated location probabilities. They are not directly comparable to earlier raw-frame Student-t scores.

The optional scan clock has modest score effects and changes no site ranking here. Posterior mean unexplained-track fractions are approximately 1.7% at the 100 Hz setting in the control and essentially zero elsewhere. Improvements are therefore not simply caused by discarding most bad tracks; nevertheless the broad-null model/rate remain uncalibrated.

## What is implemented

- Joint sampled identities, including an unexplained-track state.
- Historical age-conditioned signed timing prior, applied once per satellite, with shared time across assigned tracks.
- Satellite timing marginalized at each identity decision, rather than choosing the minimum-RMS timing.
- Optional shared scan clock.
- Analytically integrated, proper per-track constant-frequency-offset prior.
- One-second block averaging as an initial dependence sensitivity, with longer tracks contributing more blocks without a second frame-count multiplier.
- Matched frozen-identity and no-clock controls; two noise settings and two differently initialized chains for the main model.

## Why it is not ready to trust as a posterior or deploy

1. **Inference exploration:** every scan has at least one setting/track with disjoint assignment support between the two chains (maximum total variation 1). Aggregate chain score differences are smaller, but that does not certify convergence. Identity probabilities are exploratory.
2. **Timing support:** ±120-second conditioning omits up to 2.65%, 5.23%, and 2.65% historical prior mass in the three scans. This is reported, not repaired; proper tail handling and support convergence remain required.
3. **Dependence:** there are 415, 235 and 299 within-track second bins containing both train and evaluation observations. Averaging within partitions does not remove this dependence, nor receiver/track overlap. Predictive claims remain retrospective.
4. **Calibration:** GLRT-to-noise mapping, scan clock, null rate/scale, and broad CFO prior are not externally calibrated. Gaussian block likelihood with a track-level null mixture is not the earlier per-observation Student-t likelihood.
5. **Candidate and location selection:** earlier training-selected shortlists and published evaluation-selected locations are reused. No claim about full-catalogue association probabilities, fresh holdout accuracy or improved geographic fixes is justified.

## Recommended next bounded iteration

Prioritize blocked/tempered assignment moves and check reproducible posterior exploration. Then calibrate residual covariance and GLRT-quality noise using separate historical groups, with whole source/time groups kept together in fresh holdouts. Add prior-support convergence tests and a more faithful orbit-to-Doppler uncertainty mapping. Only after those checks should we compare new independent-prior geographic searches. Do not compensate for these issues by adding aggressive superlinear track weights or unrestricted quadratic drift.

See `PROTOCOL.md` for exact settings, `RESULTS.md` for every score and inference diagnostic, and `results.json` for per-track probabilities and input/code hashes. Reproduce with `run.py` under the installed API Python environment, with OPENBLAS_NUM_THREADS=1 and OMP_NUM_THREADS=1. The runner is restricted to the three specified session IDs.
