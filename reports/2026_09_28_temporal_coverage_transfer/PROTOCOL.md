# Shared position across broad temporal panels

Use exactly the completed eight-record timestamp panels in temporal_coverage_models.
Two fixed models: shared-track multivariate Student-t4 scale100Hz with diagonal
scale matrix, and the same model with10-second decay and20% nugget. Preserve
original offset prior, catalogue normalization, eligibility and visit partition.

Fit one location with independent record timings for all24 recordings and each
of three16-record leave-one-dataset-out source pools. Source starts are the
qualified same-model separate-panel positions of included datasets only, with
their respective fitted record timings. Three starts for all24; two for each
excluded pool. No target data or reference coordinates select source starts.

Select maximum training score among successful interior fits with gradient
infinity norm <=0.01. Bounds +/-12km, timings +/-5s. L-BFGS-B maxiter140,
maxfun200, ftol1e-14, gtol1e-8, maxls30. No retry or relaxed qualification.
At each selected donor position adapt target timings and offsets with geography
fixed, using timing starts0,-2,+2 and target training observations only.
Select target nuisance fit by training score under the same qualification.

Replay source and target held scores against their same-model separate panels
and the independent separate-panel baseline. Verify track sets and counts.
Check source position gradients against full-objective differences at1m/0.5m,
tolerance0.002. Score geography only after fits and held checks are sealed,
using the same exposed unsurveyed reference; do not treat it as surveyed truth.

Each scientific process capped180s/4GiB with BLAS1/nice19, at most two workers.
No RF, IQ reads, propagation, provider fetch or new candidate selection.
Preserve every failure and all distinct local modes.
