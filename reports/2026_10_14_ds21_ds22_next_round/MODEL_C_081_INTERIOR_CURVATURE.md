# C081 local-curvature qualification

The current C081 training-selected native-clock endpoint has positive full and nuisance-profiled position curvature at both tested finite-difference steps. As with C053, this diagnostic finds no local saddle warranting another routine optimizer continuation. It does not prove a global minimum or establish correctness of the frequency/observation model.

The exact frozen objective is 26043.283318164 and NLL is 25638.756309325. Maximum scaled gradient is 0.0003112203. The 82-dimensional state is 3.163428 km from its original 25 km search-disk center; minimum physical constraint slack is 5.989599. All prescribed probes were strictly feasible, and initialization changed no parameter.

| Scaled finite-difference step | Smallest full Hessian eigenvalue | Position eigenvalues after locally profiling nuisance |
| --- | ---: | --- |
| 1e-4 | 0.249933730 | 6.612875758, 38.498489568 |
| 5e-5 | 0.249893012 | 6.788233306, 38.629407831 |

No negative or numerically zero full/nuisance eigenvalues were detected. Relative full-matrix step difference was 2.28089e-5. The position eigenvalues changed by about 2.58% and 0.34%, respectively, so their precise magnitudes should not be overinterpreted. Their signs agree. There was no eigenvalue regularization. These objective curvatures are not calibrated position uncertainties.

The bounded run completed 329 objective/gradient evaluations and zero fits in 32.767 seconds, without reference or held-data reads. It reused the component tested in `tests/analysis/test_model_c_feasible_curvature.py` (three passing tests); the new driver passed Ruff. Source commit: `370779602`. An initial invocation used a nonexistent output path and failed its protocol read before claiming a launch or doing scientific work; the correctly frozen experiment below ran once.

Frozen experiment: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-c-interior-curvature-081-v1`.

- Result SHA256: `4df1c3f15561656005383e5c580c2003957c30c4c380301a089af28cb70948f2`
- Seal SHA256: `b307b71566953c5a6800b4ee332d42c047c1e249705c40da01888c139e8fecb8`

No cohort scores or selected estimator were changed. The next substantive investigation remains observation-model adequacy and physical RF/calibration provenance, rather than another identical local fit.
