# Execution attempts

The first pilot ran as PID 740750 with executed source SHA-256
`8b1ce03622b62231a26bd92e2a3c1adfe84fdf91bd7cf237cbcce21be781cde7`.
Its unchanged source is preserved as `run_pilot_attempt1.py`. The primary agent
verified the process active repeatedly, then absent. The expected final file
`/tmp/leo-train-causal-phase-rate-pilot.json` was absent and the original tool
session could no longer be polled. The process exit reason was not recovered;
no numerical result from this attempt is claimed. Subagents also encountered
a usage limit during this interval, but that does not establish the process's
exit cause.

The second attempt adds progress messages and per-arm partial checkpoints to
the same numerical implementation, with no change to the model, objective,
input selection, initialization, or solver settings. Numerical-library thread
counts are limited to one using OPENBLAS_NUM_THREADS, OMP_NUM_THREADS, and
MKL_NUM_THREADS. This operational change follows observed use of 47 process
threads, not any position-error evaluation. Standard output/error are preserved
at `/tmp/leo-train-causal-phase-rate-pilot-attempt2.log`; the fresh final output
target is `/tmp/leo-train-causal-phase-rate-pilot-attempt2.json`. A partial
checkpoint is not proof of completion of the four-arm experiment.

Attempt 2 completed the first arm's fits, then failed writing its first
checkpoint: `rate_at_bound_count` was a NumPy int64, which JSON rejects. Its
source is preserved as `run_pilot_attempt2.py`. Attempt 3 converts that count
to a native integer; a targeted mocked-optimizer test exercises actual fit
output serialization. No model or numerical calculation changes. Attempt 3
uses fresh `pilot-attempt3` log/result paths with the same one-thread settings.

Attempt 3 completed all four arms. Its saved result SHA-256 is
`0ec3fdddc195d60fc30ef0b9a242c02d6161145cdcd13672848b6186d43de868`.
Both first-group rate fits exhausted 60 evaluations; both second-group rate
fits converged at 20. All held-perturbation checks passed and worst per-track
profiled quadratic-versus-exact discrepancies were below 0.02 Hz.

Before any geographic reference-error evaluation, `run_convergence.py` repeats
the same four arms with a 300-evaluation maximum, preserving all model/input
choices. It also records optimizer termination, cost, and optimality. This is
a numerical convergence amendment, not parameter selection using held RF or
geographic error. The 60-evaluation result is preserved separately.
