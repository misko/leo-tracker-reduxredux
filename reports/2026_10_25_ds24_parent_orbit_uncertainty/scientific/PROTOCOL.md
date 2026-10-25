# Active-parent retained physical-prior control

DS24-0010–0013 are already exposed development data. Add the original three
physical Gaussian modes once per active curved/predictive family that lacks
them; preserve every old coordinate, likelihood ID, candidate, alias and prior.
The old 300-Hz curved constants remain at their original indices. Zero extra
variance means zero design columns, including in predictive covariance.

Original calibration support remains frozen. Full likelihood uses the new
covariance and its conditional posterior. Conservative gate/extension views
omit new physical posterior means and retain original owner/alias/visibility,
RMS, slope and noise-structure predicates. Literal expanded/full-mean gates are
reported independently. They never select the favorable interpretation. The
literal legacy postfit extension is unavailable because it assumes contiguous
physical coordinates. New nuisance posterior means are not qualified orbit
corrections; a source identity is not validated by this experiment.

Before any position fit, evaluate both models at the old saved endpoints and
axis offsets ±0.01 and ±0.02 km. Save actual −2ELBO components/gradients, finite
difference convergence, full and gate-view residual RMS, and local mean-design
information. The primary information control appends only B to OLD J/weights,
Gamma/phase precision and coefficients; its covariance is K_old+B B' and its
information cannot increase. Curved and old predictive data share all common
latent columns, with separate predictive 300-Hz constants and the unchanged
unseen Gamma inverse-moment factor2. Dense covariance checks use a fixed row
panel solely for algebra validation; every real row remains in scoring.

Materiality is predeclared: any case with BOTH c arms having movement proxy
norm at least0.05 km OR BOTH arms at least5% original-weak-axis variance change.
The proxy is −0.5 I_old^-1 (g_new−g_old), with actual −2ELBO gradients and a
2 I_old Hessian approximation. This allocates work; it does not adopt a model.
Do not combine different criteria across arms. Actual gradients must agree
between .01/.02 steps within max(.001,.001 norm(g.01)) objective/km; mean
Jacobian relative discrepancy<=1e−5. Missing or failed checks block that pair.

Only independent preflight plus explicit coordinator fit-stage authorization
permits all four paired cases: at most16 fits, cold [0,0], five phase rounds,
48 iterations each, original25×25 km bounds. Preserve unclipped absolute phases
for validity; clip only the next linearization reference. No retries, rescue,
replacement or candidate nomination. Two workers, one BLAS thread each;
600 seconds cumulative scientific worker time including producer numerical
checks,120 seconds per case across fixed+fit stages. Every failed attempt and
partial raw endpoint remains saved.

The operational reference remains the original baseline in every case. A
hypothetical research policy adopts only after conservative paired gates,
phase/Gamma convergence and complete original accepted-ID preservation in
BOTH arms, including postfit IDs. Otherwise it returns that exact reference.
The archived retained union includes likelihood IDs even at unqualified raw
endpoints; raw gate-accepted IDs and actual likelihood IDs are also separately
saved so a retained count never implies qualification. Report postfit family
relabels. Geometry is evaluated only after an audited RF seal and root release;
no geographic outcome enters this protocol or numerical triage.
