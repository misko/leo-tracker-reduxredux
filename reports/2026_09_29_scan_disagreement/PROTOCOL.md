# Local source-score disagreement diagnostic

Use the same 24-scan DS7/DS8/DS9 source pools and their existing qualified N24
training fits. Evaluate each scan's three-dimensional training score gradient
and observed negative Hessian at that point. Compute Hessians by differencing
analytic gradients with steps .001 km, .001 km, .0001 s; repeat at half steps.
Require relative Hessian discrepancy and asymmetry below .01 and positive
timing curvature. Preserve any failures rather than forcing positive matrices.

Profile scan timing locally: Hxy = Hgg - Hgt Htt^-1 Htg and
gxy = gg - Hgt Htt^-1 gt. Compare the gradient sum of the previously selected
eight scans and of all three balanced controls. Where summed Hxy is positive
definite, compute Hxy^-1 gxy as a local predicted displacement from N24 and
compare to the already measured fitted displacement. This is retrospective
diagnosis of the selection failure, not a new estimator or calibrated error.

Check that summed per-scan scores and gradients replay the pooled model.
Do not use reference error, target prediction or held observations for these
derivatives. No new location fit, tuning, RF or production changes. Three
workers with 180-second caps. Report all datasets and all four subsets.
