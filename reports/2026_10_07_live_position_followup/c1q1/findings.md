# C1-Q1 on a live regional scan

The bounded comparison does not support replacing T1AT. On the October 6 22:52 UTC scan (`scan-fw-ffe5accf2d020263`), the score-selected C1-Q1 position is worse in both RF arms despite lower posterior frequency RMS. All four selected fits converge.

| Model | Final RF arm | Position error | Posterior RMS | Selected basin |
|---|---|---:|---:|---|
| T1AT | fitted c | 497 m | 140.1 Hz | −75, −75 km |
| T1AT | c = 0 | 542 m | 150.3 Hz | −75, −75 km |
| C1-Q1 | fitted c | 3,835 m | 128.3 Hz | −93.75, −93.75 km |
| C1-Q1 | c = 0 | 2,229 m | 143.9 Hz | −75, −75 km |

![Selected accuracy and frequency fit](comparison.png)

This is a single-scan regional-proposal diagnostic, not a new regional search or independent validation cohort. It uses every original passing top-one GLRT window, including clutter/unassigned windows, the original archived TLE, and all six successfully archived final basins. No region or seed is chosen using roof position. Roof coordinates enter only the reported error.

For each basin, both archived T1AT fitted-c final vectors (associated and zero-timing initialization histories) form the same fixed seed pool for T1AT and C1-Q1, fitted-c and c=0. These are full-data warm starts originally optimized under T1AT, which favors the control's initialization. Each new fit has the same five-second and 300-iteration limits and original local disk. Selection minimizes each model's own objective plus the frozen calibration penalty across all basin/start results. Raw objectives across the two models are not comparable performance measures.

The C1-Q1 implementation preserves T1AT's frequency sigma 200 Hz, detection budget 0.8, clutter rate 2, and common timing sigma 10 seconds. It changes relative timing sigma to 1/3 second and replaces the hard horizon with the historical quintic ramp from 0 to 1 degree geometric elevation. Both frequency and detection-probability gradients include the finite-set nonempty normalization. Position chart derivatives retain the original 1 m central differences; orbit interpolation derivatives remain piecewise analytic.

All 48 bounded fits completed in 108.48 seconds; 43 converged. Twelve archived T1AT objective evaluations reproduced their saved values to the asserted 1e-6 tolerance. Five meaningful tests cover hard-gate likelihood parity, probability normalization gradients, gate support, full position/nuisance/timing gradients, and horizon/domain agreement. A separate Sol agent independently reviewed the implementation and reran the tests successfully.

The RF comparison is controlled within each basin: observations, candidate bank, baseline, other priors, seeds and budgets match. The receiver baseline and association remain shared products of the original fitted-c pipeline; this removes only the final residual RF coefficient. Independently selected final basins differ between the C1-Q1 arms, so their selected-error difference is not a fixed-bank treatment effect. Posterior RMS also changes weights between models and is not a common held-out metric.

Artifacts: `results.json` contains every fit, seed identity, objective, diagnostics and numerical provenance; `summary.json` contains score-selected results. `../heldout/verification.json` independently verifies this scan's capture/analysis/window evidence, complete original TLE candidate list and checkpoint binding. The shared loader received additional provenance assertions after these fits; that hardening does not change numerical input construction.

No production scoring/default, public contract, RF collection or acquisition evidence was changed. The tested adapter remains a research prototype. A larger fresh-ephemeris comparison should use training-only proposals and calibration with an independently reserved confirmation set before considering model promotion.
