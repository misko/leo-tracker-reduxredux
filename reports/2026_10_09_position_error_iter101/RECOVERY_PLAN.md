# Lean recovery of failed retained regions

The ac11 diagnostic establishes a specific causal opportunity: the ordinary search
already retained a region that was lost during calibration. Qualifying its saved
calibration, then using ordinary association, matched c finals and unchanged B7,
reduced final error from 55.685 to 1.031 km fitted-c and 53.945 to 1.927 km zero-c.
This is consumed single-scan evidence. It does not establish a broadly safe default.

## Operational gap and minimal change

[Current recovery](../../src/leo/application/hard60_recovery.py) gathers failed
points only when `spacing_km == config.levels_km[0]`. Its retained-region recovery
then requires membership in that coarse-point candidate map. A failed retained
fine-grid calibration can therefore never enter recovery, even when it has the
best ordinary score. The original candidates and immutable stage receipts remain
valuable controls and must remain intact.

Add a narrow recovery path for **ordinary retained regions whose calibration
failed**, at any grid level. Do not retry every fine-grid point. Trigger from
ordinary retention and inference diagnostics, never reference error, known receiver
coordinates or a hand-selected scan ID. Preserve the existing coarse recovery path
as a separately recorded policy during initial evaluation.

For each distinct failed retained region, retain the exact ordinary coarse and
returned calibration vectors. Reconstruct the same observations, bank, receiver
correction and priors; verify stored objective binding before refinement. Apply
one bounded direct reduced-Hessian polish to a feasible unqualified prefit, then
run the ordinary receiver correction and fixed-position postfit. Apply the same
bounded polish only if that postfit remains independently unqualified. A missing
or infeasible state is an explicit failure, not permission to invent a new seed.

The refinement changes no model dimension, likelihood, hard60 bound, sigma or
acceptance gate. Use the frozen full projected KKT threshold 0.001 and fixed
initial-objective 128-ULP ceiling. Preserve every trial and failure. If qualification
fails, preserve the ordinary outcome. Active-face methods cannot release wrongly
active constraints; an unsuccessful refinement is not evidence of mathematical
nonconvergence. The original optimizer's success flag alone is insufficient.

Qualified shared calibration feeds ordinary association and both matched c arms
with identical bank, observations, priors, local region and fit budgets. Append
these finals to the candidate inventory. Preserve all original ordinary candidates;
use the existing [regional winner policy](../../src/leo/application/hard60_b7.py)
with its calibration penalty. Do not compare scores between different B7 nuisance
models or use a smaller reference error to select a stage. Replay ordinary-only
and augmented candidates in disjoint checkpoint namespaces.

## Cost and why the research chain is not the algorithm

Iterations93–100 investigated alternatives sequentially; deployment must not run
that whole chain. Iteration100 used one 21-dimensional active-tangent reduced-Hessian
round and 46 objective/gradient evaluations to qualify the saved corrected endpoint.
That is a cost observation at that endpoint, not the cost of direct recovery from
an ordinary start. The proposed direct102 test must measure whether the same fixed
algorithm works without depending on successful96/99 intermediate refinements.

Freeze an objective-evaluation cap and a wall-time cap per polish before any broader
run. Record realized evaluations, reconstruction time, linear-algebra time, total
wall time and deferred work. Deduplicate the same retained region across separation
passes by physical model/input binding. Cap the number of recovered regions using
the ordinary retained-region budget, not per-scan error or tuned thresholds. Keep
the pipeline resumable through its stage port. Numerical methods remain analyzer
components without storage, CLI, HTTP or PostgreSQL dependencies.

## Qualification and evaluation sequence

1. Synthetic component tests cover coupled active timing faces, interior states,
   fixed position/RF locks, rank deficiency, finite/budget failures, fixed ULP ceiling,
   objective binding and unchanged full KKT. Integration tests enforce shared
   calibration, all c-arm starts, append-only receipts, original candidate retention
   and disjoint replay caches. Golden fixtures require explicit review.
2. Complete the frozen direct-start102 ac11 experiment. An iteration100 endpoint
   success alone is insufficient. Report every attempt and whether ordinary
   association/model selection reaches the rescued region. Do not tune the policy
   to achieve ac11's reference position.
3. Freeze one generic policy, then evaluate all DS16 **63**, DS17 **51**, DS18 **34**
   members plus the **45 newer development recordings**, using their authoritative
   membership inventories. These are 193 membership rows before documented overlap
   accounting, not automatically 193 independent captures. Account explicitly for
   DS16's 15 members outside its old48 subset. Include missing input/analysis and
   unqualified outcomes; do not filter by readiness or quality.
4. Per dataset/cohort and matched c arm, report baseline/candidate mean, median,
   p95, worst, paired regressions, trigger rate, rescued-region qualification,
   winner changes, fallbacks, failures and runtime/evaluation distributions.
   Report frequency fit/support separately from position accuracy. Plot paired
   errors and tail distributions; show all failures and trigger-negative controls.
5. Evaluate eligible failures and nontriggered members under the same frozen rules.
   Nontriggered scans should reproduce baseline. A geometry-wide success is stronger
   than repeating the consumed ac11 success, but consumed-data tuning must remain
   disclosed. DS18's previously consumed members and unmatched-registry members
   cannot be relabeled unseen validation. Closed reserves remain closed.

No new RF collection or reference-guided seed, bank, retention, per-scan threshold
or winner selection is authorized. Reference coordinates belong only in subsequent
post-fit evaluation reports. Broad deployment requires measured regression and
cost evidence from this frozen general rule; a single rescued example is not enough.

Inventory qualification: [the metadata inventory](INVENTORY_README.md) covers all
193 membership rows, but the newer cohort contains six B7 and 39 older hard60
documents. Their archived results are not a matched B7 baseline. Explicit baseline
bindings are presently available for only 17 DS16, 51 DS17 and 10 DS18 members;
70 missing bindings remain explicit. Public checkpoint extraction and a matched
ordinary-only B7 replay are prerequisites where necessary. Nonbaseline separation
passes expose failure metadata without complete retained-region geometry; do not
infer their recovery eligibility or fine-grid membership from the baseline pass.
