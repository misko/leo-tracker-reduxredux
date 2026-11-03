# Completed greedy evaluation handoff

All 64 independent DS9/DS10/DS11 primary attempts are complete and sealed.
No fitting or propagation workers remain active.

- Primary frozen T4 joint greedy: 51/64 accepted, median1859.68m.
- One separately recorded continuation for all13 unresolved winners:
  63/64 accepted, median2057.64m, worst12307.97m.
- DS11-F087 reached its iteration cap after48iterations with129.65s spent.
  A separately recorded post-hoc third-stage diagnostic used14 more iterations and
  14.02s, converged at2066.89m error, total143.67s (<180).
  All64 now have converged results; descriptive median2059.90m.
  Do not relabel the original primary or two-stage experiments as64/64.

README.md contains the final explanation, caveats, tables, and figure links.
primary-evaluation.json, continuation-evaluation.json, result-summary.json,
scan-errors.csv, polish-summary.json are the evaluator artifacts.
primary-audit.json and continuation-audit.json pass. Independent polish audit
is in polish-audit.json. Exact sources are archived in primary-source/,
continuation-source/, and polish-source/. All earlier attempts remain preserved.

The user specified100ft (30.48m) ABOVE MEAN SEA LEVEL; a bound NOAA GEOID18 grid
converts this to candidate-dependent approximate ellipsoid height. No receiver
GPS initializes any scan. Every scan uses the same flat250km Sacramento disk.
The original sequential height-only controls were264–312km wrong; broad search,
joint refitting/reassignment, and robust normalized Student-t likelihood were
needed to obtain useful results. This is a regression panel, not unseen validation.
Do not claim calibrated confidence, global optimality, or standard-pipeline
deployment.

Tests: full owned pre-polish suite58passed; new polish4tests and continuation
plot3tests passed. Final plot additions have their own tests. Scientific fitter
sources and the old immutable Gaussian-sum implementation remain unchanged
after freezing; no golden fixtures were changed.

Orbit preparation failed once for DS10-F131 because a full-catalogue satellite
crossed an export admission-radius cutoff outside the original interval.
Its SGP4 states were finite/error-free and it was absent from the fit union.
The failure and recovery are preserved in orbit-prep/. The utility now records
such post-admission crossings, preserving fullIDs/order/originalsamples.
The only other crossing was DS9-F080; also absent from its fit union. The
independent primary audit verifies those facts explicitly.

Remaining scientific improvement is kilometer-scale accuracy, multimodal
association ambiguity, and uncertainty calibration. The current prototype
numerically converges on this64-scan regression panel with the disclosed final
diagnostic. Existing greedy_joint_location.py and report entrypoints implement
the experiment; the old Gaussian-sum algorithm has not been replaced or deployed.
