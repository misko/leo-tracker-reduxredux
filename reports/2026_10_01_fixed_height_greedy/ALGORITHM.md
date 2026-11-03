# Joint greedy localization with fixed sea-level height

Each scan starts independently with a uniform horizontal prior inside a
250 km disk centered on Sacramento. Receiver GPS enters only the evaluator.
Height is fixed at 30.48 m above mean sea level; NOAA GEOID18 supplies the
location-dependent conversion to approximate ellipsoid height.

The fitted variables are horizontal position, a shared receiver clock offset,
two receiver drift terms, and satellite epoch offsets. Clock and drift/epoch
variables retain their original zero-mean Gaussian priors. Satellite identity
is a discrete unknown for each retained track; background is another choice.

For state x and track assignments a, the objective is

    J(x,a) = nuisance_prior_penalty(x)
             - sum_tracks log[association_prior(a | x)
                              * track_likelihood(track | a,x)].

Every retained physical track appears once. The experimental likelihood is a
normalized multivariate Student-t with four degrees of freedom, for both signal
and background. Its scale matrices equal the earlier Gaussian covariances;
its actual covariance is twice that scale. This choice is not calibrated.

The algorithm has three steps:

1. Score a broad spatial grid using every track and summed satellite/background
   likelihoods. Refine geographically separated basins and retain three seeds.
   These seeds initialize an optimizer; they do not replace or multiply the prior.
2. At each seed, choose the best satellite/background assignment per track, then
   jointly update position and nuisance variables. Student-t weights reduce the
   influence of large residuals. A line search accepts only objective decreases.
   Recompute assignments and repeat until both assignments and state stabilize.
3. Select the lowest objective across all attempted seeds. If that winning seed
   has not converged, report unresolved even if a worse seed has converged.

The primary run allows 90 seconds per scan. An unresolved winner can receive one
separately recorded continuation, for a combined maximum of 180 seconds. It
resumes numerical optimization using the same observations and original prior;
it does not reuse a posterior as a prior or add the observations a second time.

This is a search for a local hard-association mode. It does not produce a
calibrated location distribution or prove that the global mode was found.
Numerical convergence, position error, and uncertainty calibration are distinct.
The selected 64 recordings are a regression panel that includes development
examples, not an untouched validation set.

The earlier geographic/height check asked whether a component's uncertainty
support stayed within the allowed region and height range. Failing that check
did not directly measure horizontal error. Fixing height removes the vertical
degree of freedom, but the isolated controls still localized hundreds of
kilometers away. The joint search and robust likelihood address additional
association and residual-model problems; improvements cannot be attributed to
fixed height alone.
