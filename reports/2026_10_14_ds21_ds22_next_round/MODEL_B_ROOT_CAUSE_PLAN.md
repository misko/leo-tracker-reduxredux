# Model B: consistent-version ranking and next diagnostic

The algorithm called B in the shared-six comparison is the existing Hard60
absolute frequency mixture with common receiver clocks and free receiver band
contrasts. Shape-only localization supplies geographic proposals; it is not the
final Model B algorithm. This distinction is explicit in `ds21_baseline.py`,
`channel_group_refinement.objective`, and the shared-proposal report.

Rank the complete five-recording `baseline-shared-six-proposals-v1` matrix using
its selected fitted-c CH1–8 estimates. Do not replace individual rows with a
different version's result. The exact saved error joins give:

| Rank | Recording | CH1–8 km | CH1–4 km | CH5–8 km | All-view training-selected proposal |
| --- | --- | ---: | ---: | ---: | --- |
| Best 1 | DS21-005 | 1.271893 | 1.802316 | 2.816982 | shape-high |
| Best 2 | DS21-003 | 2.346276 | 5.332911 | 0.845484 | cold-0 |
| Middle | DS21-001 | 2.491630 | 2.357120 | 2.326932 | cold-0 |
| Worst 2 | DS21-023 | 5.599817 | 29.635673 | 10.458750 | cold-2 |
| Worst 1 | DS21-039 | 8.599847 | 2.917469 | 20.117621 | shape-low |

These are development outcomes against a configured reference, not independently
surveyed ground truth. References enter after the original training selections.
The table is descriptive and does not define a reference-dependent selector.
Each half inherits the all-training candidate/proposal pipeline. Combined B is
better than both halves on 005 and 023; it is worse than one half on 003 and 039
and both halves on 001. No universal combining benefit follows.

The separate frozen expansion baseline for DS21-025 gives B 8.315280 km all,
3.385533 km low, and 0.588376 km high. Its selected all fit reaches a satellite
timing constraint, with minimum slack 1.066e-14, while both geographic disks
remain inactive. This is a combining regression and a concrete reason to check
timing attribution, but 025 cannot be inserted into the older five-recording
ranking. The 013 and 009 coverage experiments likewise belong to separate
versions. DS22 has no validated Model B receipt in this review; no DS22 outcome
is claimed.

## Evidence and causal uncertainty

The B-specific residual-calibration assessment already reports substantial
nuisance/position confounding at DS21-005: complete-data local horizontal scales
rise from about 0.017–0.019 km with nuisance fixed to 0.301–0.356 km with all
nuisance profiled. Its timing shifts are fitted allowances, not measured orbit
or UTC errors. Tightening the relative timing prior repeats a documented risk:
accurate geographic modes can lose because weakly supported timing modes are
expensive. Do not choose a timing constraint from station-reference error.

The DS21-039 native Model C factorial provides separate motivation: timing
compensates much more displaced-position likelihood than calibration alone.
Those magnitudes do not establish the same mechanism in B, whose clock and
observation likelihood differ. That model-specific attribution is the next test.

Carrier RF scaling, receive-time conversion, simple RF relabels, generic
reweighting, receiver RF contrasts and boundary-incidence controls already have
negative evidence. Repeatability of fitted band coefficients also lacks physical
RF-path and cross-band emitter provenance. Neither another blanket calibration
extension nor a hardware transfer prior is justified by that evidence.

## New prototype and discriminating test

`model_b_tangent_profile.py` is an array-only research diagnostic. Its adapter
`ds21_model_b_tangent_profile.py` consumes the actual Model B common-clock and
group designs, orbit prediction derivatives, satellite posteriors and wrapped
residuals at the original selected fitted-c state. It verifies exact saved
objective replay before computing the diagnostic. It uses one objective call
and one orbit derivative call per view, plus one standalone likelihood oracle
evaluation, zero optimizers, and no references.

For every predetermined recording, compare CH1–8, CH1–4 and CH5–8 under four
local profiles: nuisance fixed, calibration free, timing free, and both free.
Retain the original priors and candidate bank. Report likelihood and prior
curvature separately. Attribute the weakest joint direction to every original
whole 20-second training block with its support count and expected signal mass.
All block assignments retain the original randomized partition and seed; no
chronological holdout or selected block is introduced.

Two matrices are reported separately. Complete-data Gaussian information keeps
responsibilities fixed. Linearized observed-mixture curvature additionally
subtracts the satellite/clutter score covariance. This second matrix is exact
for the local linear prediction mixture; it omits orbit second derivatives,
visibility changes and alias crossings. Indefinite nuisance curvature is recorded
as unavailable for minimization, not inverted into a confidence estimate. Neither
matrix proves global identifiability, physical calibration, or position accuracy.
Saved constraint slack and boundary flags are retained. Profiles do not impose
the optimizer's active-bound tangent cone; such directions can be infeasible and
must receive a constrained full-objective check before causal interpretation.

If timing profiling destroys position information in B's worst cases but not its
best cases, timing/position confounding gains B-specific support. If the observed
assignment covariance dominates or is indefinite, a complete-data timing story
is insufficient. If both effects are similar across best and worst cases, this
test cannot explain the failure ranking. Group attribution can identify supported
observations for a later physical test, but it cannot justify discarding groups
or tightening a prior solely because of their reference-position effects.

The bounded wrapper `ds21_model_b_tangent_runner.py` consumes the original
shared-six parent protocols, selected terminal states and all 18 independent
fitted-c attempt receipts per recording. It rechecks the training argmin,
discovery preparation hashes and ordered bank. It freezes loaded scientific
sources, including the native extension, and binds supplied prepared arrays,
score/prior values and whole-block assignments. The caller's qualified training
preparation is explicitly separate computation, not claimed as zero cost.

Root owns real-data execution. Pass at most four predetermined cases (005, 003,
023, 039), their three original views and the caller-loader source paths to
`freeze_cases`; then invoke `run_cases` once under the 120-second internal cap
with an external TERM/KILL bound. It preserves partial outputs and failed
launches, refuses retries, verifies source/input bindings after computation, and
seals the launch, all results and terminal. The programmatic port accepts no
reference coordinates, discovery request, new seeds or changed model parameters.

The concrete CLI `ds21_model_b_tangent_cli.py` also supplies the genuine original
training loader recipe, so root does not need to construct cases. Its metadata
freeze precedes decoding and preparation. It pins the original membership,
tracking input, deployed decoder, discovery and shared-proposal protocols,
persisted orbit bank, B attempts and reachable scientific sources. Each run
recreates the original random 20-second partition, prepares the three training
views, selects the original bank and derives clock knots from original counter
coverage. It computes whole-group IDs from integer probe counters and canonical
window identities, without rounding UTC or candidate support times. Exact
preparation digests and an independently reconstructed original B Gaussian
objective, full physical gradient and satellite posterior must close before
diagnosis. Exact B objective types reject accidental native Model C inputs.

Use the research Python environment and single-threaded BLAS. Freeze once, then
queue each recording independently under external TERM at 195 s and KILL at
200 s. The internal 180-second whole-slice timer includes preparation; the
120-second inner numerical timer preserves the remaining outer timer. For
example, from the research worktree:

```bash
PYTHONPATH=src:tools python tools/ds21_model_b_tangent_cli.py freeze \
  --label DS21-039 --label DS21-023 \
  --protocol reports/2026_10_14_ds21_ds22_next_round/model-b-original-freeze.json
PYTHONPATH=src:tools python tools/ds21_model_b_tangent_cli.py run \
  --label DS21-039 \
  --protocol reports/2026_10_14_ds21_ds22_next_round/model-b-original-freeze.json \
  --output reports/2026_10_14_ds21_ds22_next_round/local/model-b-original-039
```

Queue DS21-023 with its own output directory after 039 completes; use the same
sealed metadata protocol. Neither command changes or invokes a frozen fit
runner. The run retains a failed whole-slice termination and refuses a second
launch in that output namespace. A failed preparation is never labelled a zero
cost diagnostic.

No real-dataset numerical run, new localization estimate, RF collection or
promotion is part of this implementation. A fitting intervention needs the
additional physical evidence and full-objective displacement validation that
this diagnostic may identify. This round uses fitted c only, as explicitly
requested; it introduces no new c=0 arm.

## Validation and provenance

Twenty component tests cover actual common-clock/free-group Model B adapter
replay, synthetic timing versus calibration confounding, exact linear-mixture
Hessian finite differences including clutter, nuisance-unit invariance and null
directions, likelihood/prior/group closure, explicit invalid inputs, source/group
mutation rejection, three-view source-frozen execution, sealed cache, and retained
failure without retry. Additional actual public TrackingInput tests cover the
preparation recipe, original randomized whole-block provenance, source pinning
before decoding, whole-slice preparation failures, and preserving nested alarms.
Tests use synthetic observations only. No frozen runner,
scientific core, persisted contract, golden fixture or original report changes.

Ranking sources: `reports/2026_10_13_ds21_three_models/shared-six-baseline-statistics.json`
and the corresponding five `development-errors/baseline-shared-six-proposals-v1-*.json`
error joins. Additional evidence: `reports/2026_10_13_ds21_model_b_shape/residual-calibration-control.md`,
`transfer-eligibility.md`, `reports/2026_10_13_ds21_039_root_cause/NEXT_FOUR_PRIORITIES.md`,
and `reports/2026_10_13_ds21_release_readiness/THREE_MODEL_025_RESULTS.md`.
