# Joint refinement of finite spatial probes

Before any fits, freeze all eighteen original q020 panels and their completed
spatial-profile results. For each panel, choose the highest training-score
qualified probe at 250 m and at 1 km, using stored order to break exact ties.
Do not use held scores or reference errors to choose starts. Retain all tracks,
candidate banks, masks, likelihood scales, shared position and per-scan timing.

Refine E/N and timing jointly from each selected probe. Bounds remain E/N
±12 km and timing ±5 s. L-BFGS-B uses maxiter120, maxfun180, ftol1e-14,
gtol1e-8, maxls30. No retries. Qualification requires optimizer success,
distance from all bounds >=.001 in coordinate units, and maximum absolute
gradient <=.01. Audit each spatial coordinate with .0005/.00025 km steps and
each timing coordinate with .0000625/.00003125 s steps. Every derivative
discrepancy and pairwise step disagreement must be <.002; timing stencils
must not cross .25 s interpolation nodes. Model gradient evaluation retains
the original visibility checks. Every failed result stays visible.

Replay original training/held scores and probe training scores within 1e-7.
Export both endpoints with gradients, derivative checks, coordinates and
per-track held rows. Report separation, training-score change, held change,
nominal reference error and candidate-weight changes relative to original.
Only training-qualified endpoints may compete with the original result;
reference/held outcomes never select a winner. Results within 1e-6 training
nats of baseline are treated as tied for promotion and retain baseline.
Close-score distant endpoints must be reported explicitly. This finite start
set cannot certify a global optimum or calibrated uncertainty.

Use five prelaunch synthetic tests covering joint quadratic recovery, invalid
gradients, interpolation-node rejection, held-independent selection and missing
probe rejection. Reuse the previous sequential sealed launcher: one child per
panel, timeout90s, AS4GiB, BLAS1/nice19, available memory >=5GiB. Stop the
launcher on a failed child; preserve the failure and unexecuted panels. No RF,
waveform reads, provider fetches, propagation or production changes.
