# Frozen batched-objective fit-validation specification

This protocol was written before the validation fit. It authorizes one unscored `group8-01` run and no other fit.

## Immutable inputs and science

- Plan and input artifacts are the sealed copies in `reports/2026_09_27_ds7_wave2/solver/first8-panel-v1/`.
- The selected unit is exactly `group8-01`, containing the unchanged first eight prepared recordings.
- The scientific configuration must be exactly equal to `config/ds7/baseline-wave2-ready-v1.json`: geographic and timing bounds, timing grid, starts `[0, -2, 2]`, optimizer settings inherited from the fast adapter, candidate banks, masks, observations, and all scientific constants remain unchanged.
- The optional wrapper may replace only `ds7_baseline_adapter.JointObjective` during `ds7_fast_baseline_adapter.estimate`; it must restore that global after success or failure.
- No scoring, reference, pose interpretation, raw IQ, RF collection, or production write is permitted.

## Execution bound

- Adapter wall cap: 300 seconds; total cap: 300 seconds.
- CPU threads: 1; BLAS threads: 1; process priority: nice 19.
- The runner uses the direct installed interpreter command from the ready arm. GNU `time -v` wraps the runner externally and records maximum RSS separately.

## Predeclared equivalence gate

Compare the new sealed response with the existing frozen first-eight response at `reports/2026_09_27_ds7_wave2/solver/first8-panel-v1/group8-01/response.json`.

- both status `ok`, converged flags equal and true, and boundary flags equal and false;
- east and north absolute differences each at most `1e-8 km`;
- every timing-offset absolute difference at most `1e-8 s`;
- training-log-likelihood absolute difference at most `1e-7`;
- training RMS absolute difference at most `1e-7 Hz`;
- fitted and original `nfev` and `total_nfev` must be reported, with any difference treated as an adoption failure even if the numerical tolerances pass.

The report must include adapter runtime and externally measured peak RSS. Passing this gate supports only optional computational adoption; it creates no new scientific or geographic evidence.
