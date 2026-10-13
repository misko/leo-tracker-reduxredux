# Fitted-only A/B/C expansion: seed-transfer revision

The [first expansion protocol](THREE_MODEL_EXPANSION_PROTOCOL.md) remains the
historical v1 specification. Its DS21-009 initialization failed before any
location fits. The [bounded diagnostic](PROJECTION_009_DIAGNOSTIC.md) isolated
Model B's all-channel `cold-0` projection: the original solver exhausted 200
iterations despite a physical residual RMS of 5.19e-12 Hz. Both failed v1 and
diagnostic namespaces, sources and receipts remain intact.

The v2 adapter is `tools/ds21_fitted_models_v2.py`, commit `7d83e159f`. It preserves the original
scientific objectives, priors, observations, candidate bank, proposal order,
fit budgets and training-only selection rules. It uses a new `models-v2`
namespace and binds its own source plus all original dependencies. No published
contract or frozen numerical core is changed.

For necessary Model A low-band and Model B calibration seeds, v2 first calls the
unchanged strict bounded projection. Successful results are retained exactly.
Only the specific bounded-projection nonconvergence error permits a separate
proof that the original saved source coefficients are a valid seed in the target:

- Same time/RF centers, group frame, dimensions, clock nodes and physical clock
  basis; compatible RF, baseline and group functions.
- Finite coefficients within the original drift, RF, clock and group bounds;
  valid geography and satellite-number-mapped common/total timing bounds,
  including the original fitter's strict orbit-interpolation margin.
- Independent target-versus-source physical correction closure on every training
  row within 1e-6 Hz, consistent with the existing physical export tolerance.

The fallback accepts a separately verified source seed, never the failed solver's
result and never a claimed stationary position. Any failed compatibility or
feasibility check stops initialization. Bounds are not clipped or relaxed.

Strict-success behavior matters: a rank-deficient within-band design can admit
different coefficient gauges with identical row residuals but different
cross-band extrapolation. Therefore a direct-source-first shortcut is not used.
Full Model A low/high/final fitter inputs are tested for equivalence when the
original projection succeeds, including calibration extrapolation, learned
shift, timing, nuisance, baseline and fit options.

Model A's initial high-view calibration is unused by the original sequential
core; only its satellite timing and physical high-band correction source are
consumed. Its initial all-view vector is entirely overwritten before fitting.
V2 omits these two unused calibration projections. It preserves all consumed
inputs and the required final low-function projection. Model C initialization
and its all-training receiver ambiguity lifts are unchanged.

The rollout starts with zero-location-fit initialization on DS21-009. Inspect
each seed's projection method and any exact-transfer closure/bounds certificate
before launching location fits. Then retain the original six Model A paths,
three Model B views and three Model C views: at most 54 location fits across
12 explicit units, with seven final evaluation rows. A failed sequential stage
prevents its dependent stages; failures remain in the denominator. All units
must be sealed before the configured reference enters evaluation.

The DS21-009 v2 freeze binds 411 source files and protocol SHA-256
`3ce94d22d8cccebea843f2b2d39a03426f03090f56758af2e57ee4426deb5269`.
Its parent is the unchanged generic DS21-009 six-proposal export.

Budgets remain initialization 90 seconds internally / 105 TERM / 110 KILL;
each A path 90/105/110; each B/C view 165/175/180. Fits retain 20-second,
600-iteration limits and 25 km proposal-local disks. One dataset science process
and one BLAS thread run at a time. Failed or orphan namespaces are not retried.
The half-band views retain shared proposal provenance, so they are not claimed
as independently initialized end-to-end pipelines.

The initial 20-test owned suite passed, including actual tiny A/B/C fits,
all 54 permitted calls and 12-unit sealing, seven-row reference gating, exact
successful seed equivalence, full sequential inputs, active-bound/rank-deficient
fallback checks and continued v1 readability. The strengthened sequential test
also passed separately. Independent review identified a missing strict
orbit-interpolation margin in the fallback proof; the matching original-fitter
condition and a truncated-bank refusal case were added. All 14 affected targeted
checks passed after that change; the suite now collects 21 cases. Independent
review found no remaining blocking issue, and Ruff passed. Real v2 initialization and accuracy results
will be reported separately. This protocol does not claim an accuracy gain.

Development coverage remains all 34 original fast development recordings,
followed by a frozen release and the 20 locked fast recordings. All new arms use
fitted c. The target remains below 0.5 km for every eligible CH1–8 member, with
failures counted as misses; it has not been achieved.
