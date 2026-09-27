# Conditional-LOSO temporal residual diagnostic

This post-hoc, calibration-only descriptive audit uses the six frozen
leave-one-session-out reception fits. It covers all 344 topology-retained
tracks, 6,378 reception rows, and 6,034 consecutive within-track pairs. It is
not preregistered confirmation and does not use geographic errors.

For observation `i`, the residual is `y_i - p_i`, where `p_i` marginalizes the
held fold's reception prediction over the unchanged frequency prior. Candidate
weights are not updated using held outcomes. If candidate identity `K` is
shared across a track and outcomes are independent conditional on `K`, then
`E[(y_i-p_i)(y_j-p_j)] = Cov_K(p_iK,p_jK)`. The identity-adjusted statistic
subtracts exactly this covariance before summing adjacent residual products,
then divides by the sum of the corresponding Bernoulli standard-deviation
products.

| Arm | Raw adjacent ratio | Identity-adjusted ratio | Track-sum dispersion |
|---|---:|---:|---:|
| M0 | 0.7514 | 0.7514 | 11.9062 |
| Mean direction | 0.5757 | 0.5757 | 8.9894 |
| Candidate mixture | 0.6754 | 0.6596 | 8.6730 |

The substantial positive adjacent covariance and track-sum dispersion well
above one are evidence against treating repeated reception rows as conditionally
independent with the fitted means. The mixture's intended shared-identity
dependence explains only a small part of its raw adjacent statistic. These are
misspecification diagnostics, not calibrated significance tests, and do not by
themselves select a tempering factor, correlation model, or geographic remedy.

The first exploratory calculation averaged individually standardized pair
products. Near-zero/one fitted probabilities made that summary numerically
dominated by a few pairs (the mixture value was about 74), so it was rejected
and not retained as evidence. The reported aggregate-denominator statistic is
explicitly defined above and is less sensitive to those tiny denominators.

Candidate IDs remain frequency-model associations rather than decoded truth.
Only reception coefficients are LOSO: the frozen frequency priors use all six
calibration sessions. Consecutive rows may differ by receiver and channel, and
their time gaps range from 0.120 to 13.541 seconds (median 0.963 seconds), so the
statistic is not a stationary autocorrelation parameter. Ratio residuals are
not included because matched-row selection and shared identity require a
separate joint-posterior estimand.
