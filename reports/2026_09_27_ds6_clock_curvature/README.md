# DS6 conditional receiver clock curvature: initial iteration audit

This diagnostic holds all 43 baseline locations, timings and training-selected
catalogue candidates fixed. It compares per-track constant offsets with shared
receiver linear and quadratic drift, using the sealed random whole-visit
training/held masks. No evaluation coordinate enters fitting.

The initial 80-iteration fits and 160-iteration checks are retained unchanged.
Several did not converge, and one held score changed by 37.96 when the limit
doubled. These results are superseded for interpretation by
`../2026_09_27_ds6_clock_curvature_converged/`, which repeats every scan with
2000 iterations and a 4000-iteration check. The model, assignments, priors and
initialization are unchanged.

Before real-data fitting, a synthetic constant-time test exposed an early-stop
bug: track-offset changes were omitted from the convergence check. This was
fixed; the original preflight protocol remains as `protocol-preflight.json`.
The synthetic injected-curve test needed more observations to meet its original
5 Hz recovery tolerance under the fixed shrinkage prior; its sampling density
was doubled, and a penalized-objective stationarity check was added. No real
data or scientific fixtures were altered to pass a test.

This is a conditional residual diagnostic, not a new location estimate or proof
of a physical hardware clock fault. A curved term could absorb propagation,
assignment or location error. A matched location refit is required next.
