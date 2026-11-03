# Saved-endpoint precision result

The bounded diagnostic completed in 11.45 seconds with all values finite. It
replayed the saved index-4 t8/NORAD-65855 score and gradient exactly and did not
run a position fit or inspect geographic error.

Both symmetrized observed negative Hessians are positive definite. At the
original steps, the eigenvalues are `7.49595`, `44.0243`, and `3733.99`, the
condition number is `498.13`, and relative asymmetry is `7.50e-9`. Half-step
relative asymmetry is `2.54e-6`; the original-versus-half Hessian disagreement
is `2.336e-4`. These pass the prospectively reused `0.005` symmetry and step
stability limits.

The Newton displacement is `[-6.23e-8, 4.62e-7, 2.82e-8]` in east-km,
north-km, and seconds: `0.0004666 m` horizontally and `2.82e-8 s`. This passes
the separately frozen recovery preconditions of at most `0.01 m` and `1e-5 s`.
At one Newton step, the maximum analytic-gradient component falls from
`3.57e-5` to `2.80e-6`. The quadratic predicted score improvement is only
`4.45e-12`; observed score changes across the 0.5, 1, and 2 step probes are
between `-3.24e-10` and `-5.15e-10`, indicating that objective resolution is
larger than the predicted improvement. Coordinate score-difference audits at
double, original, and half steps have maximum gradient discrepancies of
`1.33e-6`, `1.94e-6`, and `1.21e-6`.

This supports treating the saved endpoint as a stable numerical floor for the
purpose of the separately predeclared recovery probe. It does not change the
authoritative exact-screen qualification failure by itself.

Artifacts: `result.json`, `receipt.json`, and `run.log`. The receipt records one
BLAS-threaded process with a 90-second cap and exit code zero. The result binds
206 source files; all bindings were rechecked after completion.
