# Predeclared partial pooling of receiver timing differences

Evaluate all eighteen fixed consecutive four/eight panels in DS7/DS8/DS9 at
three fixed penalty scales: 0.1, 0.5 and 2.0 seconds (s010/s050/s200). Retain
all 54 outcomes. Do not choose a strength using geographic error or maximize
penalized scores across strengths. This is a sensitivity ablation, not a
trained hyperparameter selector or blind validation. Execute sequential
strength batches in the declared order s010, s050, s200.

Use the independent-RX parameter vector E/N, all RX0 timings, all RX1 timings.
For d_i = tau1_i - tau0_i and dbar = mean(d), subtract
P = sum((d_i-dbar)^2)/(2*sigma^2) from the training log likelihood. The common
dbar is profiled without a penalty. This penalizes deviations from a common
receiver difference, not deviations from zero. It is an explicit regularizer,
not a marginal likelihood or a calibrated random-effects posterior.

Keep the zero-decay shared-track-scale Student-t4/100 Hz likelihood, offset
prior, candidate banks, partitions and records unchanged. Held predictions
contain no penalty term. Persist penalized objective, raw training likelihood
and penalty separately. Training-row sums must match raw likelihood, not the
penalized objective. Existing bounds E/N +/-12 km and each timing +/-5 s remain.

Every panel/strength uses three generic starts E/N (0,0), (3,-3), (-3,3) km
and zero timings, plus the one-timing baseline's training-selected position
and duplicated timings. No warm start from free/pooled geographic results.
Select greatest penalized training score among successful interior fits
with gradient infinity norm <=.01. Same L-BFGS-B limits: maxiter140,
maxfun200, ftol1e-14, gtol1e-8, maxls30. Retain all optimizer failures and
boundaries; no retries, fallback or gate changes after launch.

Before fitting, test the penalty gradient independently with unequal quadratic
sensitivities, invariance to a common RX difference, and held-row preservation.
At each nested start require zero penalty and reproduce baseline training,
held rows and tied gradients within 1e-7. At selected points replay penalized
score within 1e-7, check raw score minus penalty identity, and verify E/N
centered differences at .001/.0005 km and timing differences at
.0000625/.00003125 s. Every analytic discrepancy must be <.002; both timing
intervals must avoid quarter-second bank nodes and their numerical derivatives
must agree within .002. Audit failures stay failed; no alternate-step review.

After training selection, report all geographic errors, held changes against
one-timing/free-RX baselines, common differences and residual dispersion,
penalties, dataset/size medians, sub-km counts and generic-only initialization
diagnostics. Full aggregates require every planned panel to pass; incomplete
subsets must be labeled and matched across models. Retain late DS9 eight.

One scientific worker, BLAS1/nice19, 4 GiB address-space and 180 s process
caps, >=5 GiB available memory before each job. Execute one strength batch
per invocation; use existing cached inputs only. Freeze hashes and preserve
receipts. No RF, waveform, propagation, provider or production-component work.
