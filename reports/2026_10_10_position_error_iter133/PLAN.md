# Matched positioning sensitivity to sub-bin frequency refinement

Preparation only. No positioning reconstruction, objective call or fit has run for
this iteration. The purpose is to test whether the cheap frequency estimators from
125/127 improve localization on recorded evidence, not merely their own RF score.

Use exactly the twelve recordings already fixed in 110/117/128, four from each of
DS16, DS17 and DS18. These are consumed development data. Do not choose members,
refiners, parameters or starts using their reference errors. Keep both immutable
125 refiners: three-bin log-power parabola and at most three local Newton steps.
Do not choose a refiner separately for each recording or observation.

Wait for all 128 terminal coverage receipts. Each original positioning observation
must have exact original-scorer and coarse-spectrum parity before either refined
value is usable. Bind every window ID and observation-order signature. Report all
missing, failed, resource-limited and parity-failed rows. For this first controlled
sensitivity, a member with any missing required refined observation is an explicit
unavailable comparison; do not silently drop rows or impute original frequencies.

Reconstruct the ordinary archived B7 model through the audited, reference-free
131/132 input path. Inherited legacy reference-error equality admission is not
permitted. Prove the original model's objective and physical input signatures
match the archive before any candidate fit. Reference coordinates and errors are
available only to a separate evaluator after all selections terminate.

Compare three measurement sets: original frequencies, log-parabola frequencies,
and Newton frequencies. Change only the measured frequency for each original
window. Apply the circular refined-minus-original residual within the established
227272.727... Hz alias period; preserve the original frequency branch and record
every seam crossing. Tests must prove this is equivalent under the existing
wrapped likelihood. No reacquisition, timing/epoch refinement or gate change.

For each measurement set run matched fitted-c and c=0 arms. All six fits start
from the same ordinary archived fitted-c B7 vector and receiver/satellite clock
coefficients, applying only the existing c=0 locks for that arm. This deliberately
differs from 130's arm-own archived starts and makes initialization matched across
both measurement variants and c arms. Keep
the original observations, candidate bank, assignments' available support, timing
priors, hard60 constraints, fitted-led calibration and correction basis, nuisance
priors, local search region and independent convergence gate unchanged. Candidate
responsibilities may change through the existing likelihood. No cross-variant or
cross-arm warm starts, truth-guided starts, retries or per-scan winner selection.

This deliberately measures final-model sensitivity with calibration and search
support held fixed. It does not establish the effect of re-running calibration,
association or regional discovery using refined frequencies. That broader pipeline
experiment requires its own predeclared protocol if the controlled result warrants
it. Likewise, a lower in-sample frequency score does not prove position accuracy.

Proposed fixed budget: 12 members × 3 measurement sets × 2 c arms = 72 fits, each
90 seconds soft budget and 600 iterations, using the existing independent physical
and clock KKT qualification threshold 0.001. At most two single-thread numerical
workers globally; launch only when a slot is explicitly free. No new RF collection.
Freeze implementation, input receipts, tests and final budget before execution.

Report all twelve member statuses and each dataset's mean, median, p95 and worst
position error; paired improvements/regressions and maximum regression; convergence,
raw failures and separately labelled archive-fallback sensitivity; frequency RMS,
score components, responsibility/support changes and actual runtime. Plot paired
position errors for both c arms and both refiners. Do not pool only successful
members into an apparently complete cohort statistic. Publish the Markdown report,
plots and integrity receipts to remote main. No deployment is authorized by this
research protocol, and the 0.4 km full-cohort goal remains unmet.
