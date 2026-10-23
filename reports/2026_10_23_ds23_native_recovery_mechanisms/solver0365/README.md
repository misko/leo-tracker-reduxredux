Bounded native optimizer mechanism comparison
===========================================

All 12 fits completed, with a 180-second alarm per fit; the longest fit took
14.31 seconds. Each solver receives the same saved ordinary persistent5s native
endpoint and saved phase reference within its c arm, runs five phase rounds and
at most 40 SLSQP iterations per round. The ordinary solver uses the same scalar
negative-twice-ELBO, bounds, finite-difference step, and stopping tolerance as
the existing constrained solver, without its inequalities. The constrained
solver is the frozen existing feasible_fit with the original native rescue
0.01 gate margin. This compares existing constraint enforcement and feasible
endpoint selection, rather than introducing a new scientific objective.

The selected persistent5s paths, original graph node, retained curved mask,
aliases, RF identities, priors, and native predictive entries remain fixed.
Saved ordinary native and published final endpoints replay with absolute
objective error below 1e-5 before any fitting. No GPS enters the fitting script;
summarize.py adds position error only after inference. No RF collection occurs.

DS23-0365: ordinary refits fail only the linear lag-one residual gate on
GRAPH_PATH_persistent5s_005: normalized slack -0.001670 for c0 and -0.000607
for fitted_c. They are diagnostics only. Existing constrained fits pass every
original gate and preserve every graph-parent accepted observation ID, gaining
40 accepted points. Their objective is worse by 14.351 / 10.121 and curved RMS
is worse by 0.797 / 0.595 Hz. Their reporting-only position error increases from
0.560 / 0.714 km to 2.915 / 2.707 km (c0 / fitted_c). Thus RF qualification and
retention do not establish improved position accuracy. The gate constraint
drives a substantial endpoint displacement in both c arms.

DS23-0041 and DS23-0272: both methods pass all gates and preserve parent IDs;
endpoints and objectives agree to numerical precision. Constraint enforcement
does not materially change these already-feasible recovery controls.

Artifacts: results.json contains protocol and complete per-case trajectories,
scalar objective terms, all gate slacks and replay records; summary.json has
coverage, report-only position errors, and pair differences. trajectories.png
plots phase-round endpoints, with no GPS reference displayed. Per-case JSON
files checkpoint the same full evidence. Gate-failing endpoints are never
recommended as accepted solutions.

Run from /home/mouse9911/gits/leo-tracker-reduxredux:

    PYTHONPATH=/tmp/algo03-feasible-deps:src:tools .venv/bin/python -B /srv/bulk/leo/research/algo04-native-mechanisms-20261023/solver0365/run_solver.py
    PYTHONPATH=/tmp/algo03-feasible-deps:src:tools .venv/bin/python -B /srv/bulk/leo/research/algo04-native-mechanisms-20261023/solver0365/summarize.py
    PYTHONPATH=/tmp/algo03-feasible-deps:src:tools .venv/bin/python -B -m pytest -q -p no:cacheprovider /srv/bulk/leo/research/algo04-native-mechanisms-20261023/solver0365/test_solver.py

Owned tests: 2 passed in 1.30 seconds. They test actual constrained gate
enforcement on a synthetic problem, then independently check replay tolerance,
matched starts/phase references, round/iteration budgets, and diagnostic labels
against completed evidence. Inputs and old output artifacts were not modified.
