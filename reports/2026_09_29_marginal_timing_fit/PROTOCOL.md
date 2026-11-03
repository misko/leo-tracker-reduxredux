# Fit location with scan timing integrated

Use the same18 first-four/last-four source-target splits as scan_holdout.
Compare the original baseline's source-only timing-profile fit with a location
fit that marginalizes one shared timing offset per source scan under the
normalized uniform[-5,+5]second prior. All source track mixtures remain q020.
No residual-slope prior or candidate re-grouping is added.

Initialize E/N at the previous source-only baseline, which used fixed starts
and no target measurements. Optimize ONLY E/N in+/-12km, max30 iterations and
50 evaluations, analytic gradients,120-second wall cap per direction. Use16
Gauss-Legendre nodes per0.25-second bank interval; audit32 at the endpoint.
Require optimizer success, no boundary, max gradient<=0.01, training marginal
score difference<=0.01 and gradient difference<=0.01 between resolutions.
Replay batched training scores and position gradients against the scalar oracle
at five timing nodes. Require score agreement<=1e-7 and gradient agreement<=1e-5.
Audit final integrated gradient by position finite differences within0.01.

Evaluate the target scans using the SAME whole-scan timing marginalization and
original q020 model as the preceding report. Reuse verified baseline target
scores, including its recorded refinement. Check new target quadrature at16/32;
numerical failures remain failures. Do not fit or initialize from target values.
Record incomplete fits and timeouts; do not tune scales or select on reference
error. Geographic reference is used only after fitting. Three local workers
maximum; no new RF or production changes.
