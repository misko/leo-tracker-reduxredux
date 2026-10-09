# Independent frequency-width experiment review

Preparation review; numerical engine not yet available at initial inspection.
No recording fits, objective evaluations or production edits performed.

The proposed globally fixed125→100Hz comparison is lean and falsifiable. It changes
the entire satellite/clutter likelihood, not just a least-squares weight. Current
`hard60_score.likelihood` uses `score.sigma_hz` in both Gaussian normalization and
residual curvature; `DynamicRFObjective.evaluate_joint` obtains its physical and
clock gradients from those same responsibility-weighted prediction gradients.
Replacing the base score before constructing B7 is the appropriate propagation
point. Verify the actual final `SlopePrior` constructor retains that score through
all superclass construction. No score override in a subclass may silently retain125.

## Engine conditions to verify before freeze

- Rebuild the exact archived B7 bank, observation ordering, receiver baseline,
  clock nodes/knots, satellite slope centers and0.5Hz/s slope prior. Archive125Hz
  objective reconstruction must pass before either width is fit. The125Hz control
  should exactly nest the production objective at the shared archived state.
- Use one shared fitted-derived physical and full clock start for all four fits.
  Copy arrays; order of fits cannot mutate subsequent seeds. Initial position must
  also define identical physical local disk constraints. Label the c comparison
  conditional on fitted-derived bank/starts, rather than independent c searches.
- c=0 locks static stretch coordinate6 **and both RF-time clock coefficients**,
  while retaining smooth clocks, timing and satellite-slope dimensions identically.
  Confirm RF-time columns remain the declared block despite appended satellite slopes.
- Test actual mixture responsibilities/normalization and physical/clock Jacobians
  at both widths, including wrapped-frequency invariance and unsigned receiver IDs
  where applicable. A residual-only Gaussian unit test does not establish mixture
  propagation. No arbitrary observation/assignment subset should replace the full mixture.
- Keep90s/600iterations, timing2s prior, hard60Hz/s, timing physical bounds and full
  independent qualification identical. Width100 must not receive extra retry or
  numerical polish unavailable to125. Preserve raw failures and actual timing.
- Select within each width by independent convergence only, then the predeclared
  fallback chain:100→qualified125→archived same-arm. Never compare across-width
  objective scores for an operational winner; their normalized models differ.
- Report paired control-versus-archive changes as well as candidate-versus-control,
  so shared-start refit effects are not attributed to width. Keep position metrics
  separate from model-specific objective, RMS, responsibilities and support.

The proposed thresholds belong in a frozen protocol before outcomes. Consumed
data can support development decisions and stability descriptions, not certify
generalization. Missing members remain coverage failures. Group/bootstrap design
must be frozen without inspecting position errors; no reserves are opened.

## Relationship to the full193 recovery extension

Do not combine the frequency-width experiment with new search recovery while
claiming a one-factor ablation. Keep the148 archived B7 endpoint experiment and
the broader recovery policy evaluation as distinct protocols until a uniformly
reproduced research baseline exists.

The five-member recovery pilot qualifies all five discarded calibrations but
changes the winner only for previously consumed ac11. Six of30 recovered regional
final attempts remain independently unqualified despite solver success. These
results justify testing the reference-free trigger on other known failure metadata;
they do not justify deploying a global policy or claiming a193-member mean.

The193 scope is63DS16+51DS17+34DS18+45newer membership rows, with documented overlap
and exposure. All must remain in coverage. A matched B7 baseline is needed for
older hard60 publications and missing bindings; checkpoint inventory preflight
should quantify cold numerical cost before fixing workers/slices. Reuse only
physically bound source receipts, preserve original candidates, and freeze the
same trigger/budgets for all eligible failures. Trigger-negative controls should
reproduce baseline and incur no candidate-only recovery work. Closed reserves
remain closed. Known/reference coordinates enter post-fit evaluation only.

## Actual engine review and synthetic likelihood checks

Reviewed `engine.py` after preparation. The shallow model copy changes only its
immutable score dataclass; the production final `SatelliteCorrection` evaluator
reads `self.score` for every likelihood/gradient evaluation. The125Hz constructor
checks exact objective, physical-gradient and clock-gradient nesting at both
archived endpoints before fitting. All four attempts copy one fitted-derived
physical/clock seed and retain identical90s/600 budgets and local bounds.

The prior RF-layout warning is resolved by actual source inspection:
`SatelliteCorrection` inserts satellite coefficients before the RF-time block,
relocates its precision/design columns accordingly, and leaves RF-time coefficients
in the final two clock entries. Thus this engine's `clock[-2:]` c=0 lock checks
match the production fitter, while coordinate6 locks static RF stretch.

The independent gate recomputes the production physical KKT and scaled clock KKT,
feasibility and objective/prior accounting. The fallback chain uses qualification
without comparing scores across widths. Resume receipts bind protocol/member/width/
arm; globally pinned reconstructed archived starts remain the source authority.

Owned `test_likelihood.py` adds four passing synthetic tests: actual125/100Hz
normalized mixture against the deployed singleton oracle and manual normalized
density, responsibility/clutter mass sum, wrapped-frequency invariance and finite
difference prediction gradients. These tests launch no fit or recording loader.
The model agent owns additional actual-model physical/clock Jacobian tests.

Before freeze, explicitly reject nonfinite objective, physical gradients and clock
gradients in independent qualification. Python `max(finite, nan)` can otherwise
mask a NaN second argument; a malformed gradient must never qualify. This was
communicated to the engine owner for a component-owned regression test.

Final pre-freeze review: the engine now asserts finite objective, physical gradient
and clock gradient before KKT aggregation. The owner added the regression and
the parent reports all16 tests passing. **No remaining blocker found for freezing
the declared research comparison.** No numerical recording fit was run by this reviewer.
