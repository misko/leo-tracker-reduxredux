# Numerical refinement of the calibration random-intercept experiment

The original calibration-only shared detection random-intercept experiment is
preserved unchanged. Its full-six artifact failed the predeclared 128-versus-256
fixed Gauss-Hermite agreement check for all three arms, so no original LOSO fits
were launched. This is an implementation failure, not evidence for or against
the scientific model.

This refined experiment changes only numerical integration. It uses
posterior-mode-centered, inverse-curvature-scaled Gauss-Hermite quadrature with
importance correction. The scientific model, frozen reception coefficients,
candidate identities and weights, feature schemas, ratio likelihood, frequency
priors, track normalization, scalar objective, sigma bounds `[0,8]`, coarse grid
`[0,.25,.5,1,2,4,8]`, neighboring-interval refinement, conditional LOSO
partitions, and advancement gate remain exactly unchanged.

Use 64 quadrature points during scalar fitting and re-evaluate every selected
training and held candidate-track detection likelihood at 128 points. Require a
maximum absolute 64-versus-128 difference of at most `0.001` natural-log units
per candidate track. Numerical failure is fail-closed, and selecting sigma 8 is
still reported as an inadequate fitted range and cannot advance.

The 64/128 orders were fixed before refined corpus fits using synthetic constant
logit stress fixtures at logits ±8, row counts 16, 60, and 120, and sigma 4.1:
32-versus-64 reached 0.00104 and failed the tolerance, while 64-versus-128 was
0.000119. A sigma-8 stress check gave a worst 64-versus-128 difference of
0.000562. These synthetic checks do not use geographic or corpus outcomes.

Run the full-six shard first and inspect numerical acceptance before launching
the six LOSO shards. Preserve and bind the original failed full artifact in every
refined shard. Report pooled M0, mean, and mixture zero/fitted joint and detection
NLL per track. Apply the original mixture advancement checks without alteration.
Calibration success is not geographic evidence and requires independent-prior
geographic validation before any location claim.
