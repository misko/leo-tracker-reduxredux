# Continuation after iteration56

Goal active, below1km not achieved. This turn made concrete progress: completed
the smooth-horizon likelihood prototype and its three derivative/equivalence
tests, rendered synthetic figure, and updated cohort report to82/148.

Iteration51 DS18 now34/34 complete; DS16 26/63, DS17 22/51 at snapshot. Confirm
current processes before any resume. DS16 exec40092/PID4001824, DS17exec53710/
PID4001840; DS18exec18770/PID4001893 may now be terminal. All completed results
must remain immutable. Rerun summarize.py as receipts arrive, publish checkpoints.

Iteration55 ordinary-start common145 experiment is live, exec3105/PID4011107.
Last observed output index10 fitted-c. Frozen187feasible starts x2arms=374fits;
5infeasible starts explicit x2receipts. Do not restart while live. Reporter uses
only completed pairs, score-selects before reference evaluation. Still consumed
development, not cohort replacement or independent validation. See55PROGRESS.

Iteration56 is only a likelihood prototype, not a complete smooth objective.
Three tests passed with PYTHONPATH=src .venv/bin/python -m pytest -q
reports/2026_10_09_position_error_iter56/test_smooth_likelihood.py.
No recording results, no score-selected rescue claim, no production changes.

Potential next implementation: add research-only elevation geometry consistent
with src/leo/analysis/_regional_orbits.cpp piecewise-linear interpolation.
Current native function returns frequency, Boolean visibility, spatial/timing
frequency derivatives, but not elevation. Need elevation and its derivatives,
including derivative of receiver up direction with candidate position. For
unit line of sight d, distance R, up u, s=d.u, elevation=asin(s):
ds/dx=-(u-s*d).site_jac/R + d.up_jac;
ds/dt=(u-s*d).interpolated_position_rate/R; convert asin derivative to degrees.
Use same observer finite-difference jacobian scale .001km; timing derivative
uses position-node slope, not interpolated physical velocity. Handle zenith
where taper is constant without dividing by zero. Test geometry vs finite
differences and native visibility, then full likelihood chain-rule derivatives
through horizon before fitting. Do not modify live frozen experiments.

Any future matched scan fits must obey54audit: known/reference coordinates and
errors evaluation-only; no per-scan tuning/bank/seeds/winner selection. Uniform
frozen bank/selection policy across DS16/17/18 and new independent validation
are required for generalization. Global Sacramento250km prior explicit. No RF.
