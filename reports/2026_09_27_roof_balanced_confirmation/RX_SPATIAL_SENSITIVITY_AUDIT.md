# RX direction evidence: association versus local precision

Read-only calibration audit while the frozen dual-effect geographic replays run.
This is a conditional sensitivity calculation, not a geographic result, a
physical antenna calibration, or a measured position-resolution limit. No model
parameters or search points were changed.

## Scales in the accepted model

The full-six mixture coefficients in `mixture_calibration_polished.json`, after
dividing by their recorded feature standard deviations, give:

| Quantity | Value |
|---|---:|
| Detection slope per unit receiver-signed east direction cosine | 7.9200175 logits |
| Matched log-ratio slope per unit east direction cosine | 1.5701301 |
| Shared detection offset SD | 2.5618598 logits |
| Independent matched log-ratio SD | 0.3249083 |
| Shared matched log-ratio offset SD | 0.2518102 |
| Marginal single-row log-ratio SD | 0.4110642 |

The accepted uncertainty parameters come from
`track_random_intercept_refined.json` and `ratio_random_intercept.json`.
They describe predictive residual uncertainty under the fitted model, not
measured physical receiver-gain variation.

For an illustrative fixed local frame and a satellite 550 km away, a 1 km
receiver displacement changes its east direction cosine by at most approximately
1/550. This corresponds to 0.01440 detection logits or 0.002855 log-ratio units.
550 km is an illustration, **not a verified minimum slant range for these
tracks**. Actual sensitivity depends on range, displacement direction, changing
satellite geometry, and local-frame rotation. This calculation must not be
reported as a bound on the dataset's achievable position error.

## What the shared ratio offset suppresses

For one known satellite and fixed nuisance parameters, write matched ratios as

    y_i = a_i + beta * east_i(position) + v + epsilon_i
    Var(v) = tau^2; Var(epsilon_i) = s^2

The conditional variance of a track's average residual is `tau^2 + s^2/m`.
For 1, 20, and 100 matched rows, its SD is 0.411064, 0.262081, and 0.253898.
Dividing by beta gives east-cosine uncertainty scales of 0.261803, 0.166917,
and 0.161705. Infinitely many repeated measurements of the same level approach
tau/beta = 0.160375. Under the illustrative fixed-frame 550 km calculation,
that last single-track constant-level scale corresponds to about 88 km.

**This is not an 88 km location-error floor.** Independent tracks can combine,
Doppler supplies additional information, and changing directions within tracks
remain informative. It explains why repeatedly observing one nearly constant
reception level does not imply kilometre-scale angular discrimination.

More precisely, for a scalar displacement q and
`g_i = d east_i / d q`, the known-candidate conditional Gaussian information is

    I(q) = beta^2 * [sum((g_i - mean(g))^2) / s^2
                     + m * mean(g)^2 / (s^2 + m*tau^2)]

The shared effect suppresses the mean-sensitivity term, but not the centered
time-varying term. This decomposition follows directly from the compound-
symmetric covariance in `ratio_random_intercept.py`; it is not an uncertainty
estimate for the actual candidate mixture or weighted search objective.

Detection has an additional distinction: its east feature reverses sign with
the anchor receiver (`mixture_calibration_inputs.py`, `build_arm`). A common
offset cannot absorb a direction change that affects RX0 and RX1 rows in
opposite ways. Therefore sigma/beta is only a scale comparison for a common
signed-direction level, not a general detection-information floor.

## Consequence for the next decision

### Within-track direction evidence is present

A further read-only calculation uses the exact joined calibration rows from
`mixture_calibration_inputs.load_joined()`. For each matched row, define e as the
east cosine averaged under the frozen frequency candidate weights, and y as
observed log-ratio minus the full-six fitted ratio nuisance prediction, excluding
the direction column. Neither directions nor weights use ratio outcomes.
Subtract each track's matched-row mean from e and y. With centered values ec,yc,
the descriptive slope is `sum(ec*yc)/sum(ec^2)`. The fixed-slope explained fraction
is `1 - sum((yc - 1.5701301*ec)^2)/sum(yc^2)`.

Across 285 matched tracks / 3,982 rows, centered east squared leverage is
47.524969, versus 234.421598 before centering (using the frozen feature mean).
Centered covariance sum is 88.762384; descriptive slope is 1.867700; fixed-slope
explained fraction is 0.356987. Thus the surviving within-track direction
relationship is positive and not negligible, despite only 20.27% of this raw
east leverage remaining after centering.

| Calibration scan prefix | Centered slope | Fixed-slope explained fraction |
|---|---:|---:|
| 39ac | 1.520 | 0.425 |
| 4c56 | 1.455 | 0.253 |
| 9d7b | 2.746 | 0.474 |
| aa97 | 3.296 | 0.431 |
| c559 | 0.945 | 0.071 |
| da28 | 1.469 | 0.319 |

All six centered covariances are positive. This does **not** establish held-out
signal strength, a physical antenna response, or fine spatial resolution: the
nuisance coefficients are fitted in sample, satellite identities are latent,
the calculation replaces the candidate mixture by its mean, and matched-row
selection depends on reception. Rows are not independent. Broad changes in
satellite direction over a track are also much larger than the directional
changes caused by a small receiver-position displacement. No diagnostic slope
was substituted into the model.

Across the 6,378 calibration rows in `calibration_directions_data.json`, the
robust top-three candidate east-cosine range has median 0.502019 and 90th
percentile 0.983748. However, after weighting by each row's frozen frequency
candidate probabilities, east-cosine SD has median 8.57e-10, 90th percentile
0.026485, and 99th percentile 0.253169. These are row-weighted descriptive
summaries, not 6,378 independent observations. Most candidate priors are already
highly concentrated, while a minority retains substantial direction ambiguity.

RX evidence can distinguish satellite trajectories whose directions differ far
more than a kilometre-scale receiver displacement changes a fixed satellite's
direction. Consequently, a location improvement may come from correcting an
association or choosing a better search basin, not necessarily sharper local
position discrimination. Both can be useful, but they are different claims.

The current geographic replay remains the direct test of distance error. If it
fails, better reception likelihood alone is not grounds to promote it or consume
the untouched confirmation cohort. A useful next diagnostic is to separate
fixed-identity spatial sensitivity from identity-switch effects, using existing
calibration/development evidence and without sharing candidates between priors.
Measured antenna orientations and a confirmed physical-to-software RX mapping
would be needed to interpret this empirical east-cosine model as a physical
antenna-response model.
