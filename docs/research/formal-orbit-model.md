# Formal fixed-identity orbit model

For observation *i* assigned to satellite *s* and receiver segment *g*, the
model is

`y_i = D_i(x, q_i + age_i r_s) + b_g + epsilon_i`.

The archived causal orbit state fixes identity and the nominal phase `q`. The
receiver horizontal coordinate `x`, segment offset `b`, and one correction rate
`r_s` per NORAD are inferred. Altitude and receiver time are fixed. The sealed
pretarget robust-AR(1) orbit experiment already contributes its predicted phase
to the state archive, so the correction prior is
`r_s ~ Normal(0, 0.09176615913014215^2) s/hour`. This prior appears once per
unique NORAD. It is not converted to an arbitrary number of radio residuals.

The implementation constructs orbit states at nominal phase and nominal phase
plus/minus one second with `clock_s=0`. It uses their quadratic interpolation
and iteratively relinearizes the phase-rate derivative. Offsets and the single
bounded rate in each independent source block are then solved by an exact Schur
elimination at each iteration. Exact SGP4 propagation of final corrections is a
required real-data diagnostic; the interpolation is not represented as exact.

Within each RF track, standardized residuals have stationary irregular-time
AR(1) correlation `rho^(delta_time/tau)`. Tracks are independent. A normalized
Student-t likelihood supplies robust tails, with fixed externally declared
degrees of freedom. Each subset estimates its own measurement scale from its
training rows under a frozen `LogNormal(log(250 Hz), 1.5)` prior and 5--2000 Hz
bounds. The fixed-250 Hz model remains an explicitly configured ablation. The
AR(1) covariance log determinant,
Student-t normalizing constant, and normalized Gaussian orbit priors are included
in the reported negative log posterior. Hyperparameters are fixed before a
target/subset fit and are never estimated from the full target fitting pool.

Segment offsets and rates are profiled (MAP), not marginalized. Reported local
position covariance is the inverse curvature of that profiled robust objective,
conditional on fixed identities and the declared noise model. It is a local
Laplace approximation from a finite-difference Hessian of the normalized
profile posterior, not a calibrated coverage claim. Singular or ill
conditioned curvature produces an explicit weak/insufficient status rather than
a finite uncertainty ellipse. Held-out frequencies are not read while fitting;
they are used only for the final predictive RMS. Evaluation rows whose segment
has no fitting observations are unsupported and excluded from that RMS.

The posterior is conditional on the 446 strict-causal fixed identities. It does
not include identity ambiguity or catalogue-tail mass. Receiver clock is fixed
to the recorded UTC basis; orbital phase rate must therefore not be interpreted
as an independently identified clock correction. The probability regions are
conditional local summaries and require simulation and independent-session
coverage measurements before they can be described as calibrated.
