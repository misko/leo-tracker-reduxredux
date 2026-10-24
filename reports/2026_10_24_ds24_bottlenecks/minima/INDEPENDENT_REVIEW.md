# Independent methodology review

Read-only review covered `../cohort_review.py`, `../information/diagnose_information.py`, `../information/report_information.py`, `../information/REPORT.md`, and the predictive-likelihood implementation in `tools/ds23_predictive_linear.py`.

The cohort comparison consistently selects `method == baseline`, which is the current ALGO02 + causal signed phase prior + cavity primary. Arithmetic half-endpoint blending and same-site error-vector decomposition are descriptive diagnostics, not adopted estimators. The fixed-GPS probe keeps observations and satellite labels unchanged, solves nuisance coefficients, and refreshes phase. All 48 final phase changes were below 1e-5 s (maximum 9.02e-6 s), so the recorded evaluation-site objective differences are not caused by reaching the eight-round cap before phase convergence. These probes do not establish model misspecification merely because the fitted endpoint has higher likelihood than the true position.

The information report clearly distinguishes curved-only nuisance projection from the curved-plus-predictive fixed-Gamma joint Gaussian surrogate. The latter includes predictive rows in a mathematical information calculation, whereas the operational calibration coefficients remain curved-only. Positive-semidefinite data ordering and nuisance-freezing controls are conditional properties of those fixed models, not guarantees that independently fitted channel subsets have ordered geographic accuracy. The report appropriately disclaims calibrated uncertainty and a fundamental CRLB.

Two small precision improvements were recommended to the parent:

- State that the actual-objective Hessian holds the persisted phase-linearization reference fixed. Coefficients and Gamma variables reoptimize as position changes; the outer phase reference is not refreshed at every finite-difference point.
- Compute Mahalanobis evaluation offsets using the exact inverse of the engine's `latlon` conversion, or explicitly label the tangent-plane approximation. Its north conversion used 111.32 km/degree while the engine uses 111.0; the discrepancy is below 0.3% and does not alter the qualitative result.

No substantive numerical overclaim was found in the reviewed report. This review did not edit those shared files.
