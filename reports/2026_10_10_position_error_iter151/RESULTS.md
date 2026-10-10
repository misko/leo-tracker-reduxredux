# Fresh native versus zero-c discovery

Consumed twelve-member conditional pilot, not independent validation. Both branches use fresh discovery and the same frozen handoff policy. Final c arms are matched within each branch. Banks can differ across discovery policies; frequency scores are not used as cross-policy position evidence.

**Predeclared progression screen: PASS.** This displays the frozen reporter's decision receipt, not a new policy decision or deployment authorization.

Criteria: complete matched endpoints for all twelve in both final c arms; fitted-c mean strictly improves over the fresh native control; no fitted-c member regression exceeds 1 km. c=0 results remain a separately reported sensitivity.

Complete comparison: True; fitted-c paired coverage: 12/12; mean fitted-c delta: -0.025763 km; maximum fitted-c delta: 0.246589 km. Positive deltas mean zero-led regression. With incomplete coverage, displayed deltas describe only available pairs and cannot pass the screen.

![Matched position errors and missing endpoints](position_errors.png)

| Dataset | Arm | Paired/members | Native mean/median/p95/worst km | Zero-led mean/median/p95/worst km | Regressions |
|---|---|---:|---|---|---:|
| DS16 | fitted-c | 4/4 | 1.0991 / 1.0220 / 1.6776 / 1.7747 | 0.9637 / 1.0541 / 1.4269 / 1.4798 | 1 |
| DS16 | zero-c | 4/4 | 1.1508 / 1.0967 / 1.5205 / 1.5929 | 0.8985 / 0.8146 / 1.2754 / 1.3564 | 1 |
| DS17 | fitted-c | 4/4 | 0.8680 / 0.8049 / 1.3439 / 1.4345 | 0.8521 / 0.8049 / 1.3439 / 1.4345 | 1 |
| DS17 | zero-c | 4/4 | 1.1845 / 1.2211 / 1.8411 / 1.8699 | 1.2075 / 1.2211 / 1.8411 / 1.8699 | 3 |
| DS18 | fitted-c | 4/4 | 1.4576 / 1.0092 / 3.0710 / 3.3893 | 1.5317 / 1.1325 / 3.0710 / 3.3893 | 3 |
| DS18 | zero-c | 4/4 | 1.6197 / 1.0755 / 3.5271 / 3.8979 | 1.6713 / 1.1747 / 3.5271 / 3.8979 | 3 |
| all12 | fitted-c | 12/12 | 1.1416 / 0.8737 / 2.5013 / 3.3893 | 1.1158 / 0.9892 / 2.3391 / 3.3893 | 5 |
| all12 | zero-c | 12/12 | 1.3184 / 1.0967 / 2.7825 / 3.8979 | 1.2591 / 0.8702 / 2.7825 / 3.8979 | 7 |

Incomplete pairs produce available-subset metrics only; full-member metrics are withheld. Missing endpoints are never imputed.

| Member | Search | Native | Zero | Fitted-c delta km | c=0 delta km |
|---|---|---|---|---:|---:|
| DS16-020 | complete | complete | complete | -0.311134 | -0.297897 |
| DS16-024 | complete | complete | complete | +0.064227 | -0.474988 |
| DS16-054 | complete | complete | complete | -0.294894 | -0.236550 |
| DS16-058 | complete | complete | complete | -0.000000 | +0.000000 |
| DS17-006 | complete | complete | complete | -0.000000 | +0.000000 |
| DS17-015 | complete | complete | complete | -0.063684 | +0.091949 |
| DS17-027 | complete | complete | complete | -0.000000 | +0.000000 |
| DS17-031 | complete | complete | complete | +0.000000 | -0.000000 |
| DS18-013 | complete | complete | complete | +0.049743 | +0.008015 |
| DS18-023 | complete | complete | complete | -0.000000 | +0.000000 |
| DS18-024 | complete | complete | complete | +0.000000 | -0.000000 |
| DS18-029 | complete | complete | complete | +0.246589 | +0.198345 |

Selected endpoints and retained-region coverage:

| Member | Branch | Qualified selected / 2 | Missing selected | Qualified calibrations / known regions | Unavailable regions | Qualified regional finals / recorded attempts | Qualified joint fits / recorded attempts |
|---|---|---:|---:|---:|---:|---:|---:|
| DS16-020 | native | 2/2 | 0 | 2/3 | 0 | 10/12 | 12/12 |
| DS16-020 | zero | 2/2 | 0 | 3/3 | 0 | 18/18 | 12/12 |
| DS16-024 | native | 2/2 | 0 | 2/3 | 0 | 12/12 | 12/12 |
| DS16-024 | zero | 2/2 | 0 | 3/3 | 0 | 17/18 | 12/12 |
| DS16-054 | native | 2/2 | 0 | 3/3 | 0 | 14/18 | 12/12 |
| DS16-054 | zero | 2/2 | 0 | 3/3 | 0 | 18/18 | 12/12 |
| DS16-058 | native | 2/2 | 0 | 3/3 | 0 | 17/18 | 12/12 |
| DS16-058 | zero | 2/2 | 0 | 3/3 | 0 | 18/18 | 12/12 |
| DS17-006 | native | 2/2 | 0 | 3/3 | 0 | 18/18 | 12/12 |
| DS17-006 | zero | 2/2 | 0 | 2/3 | 0 | 12/12 | 12/12 |
| DS17-015 | native | 2/2 | 0 | 3/3 | 0 | 18/18 | 12/12 |
| DS17-015 | zero | 2/2 | 0 | 2/3 | 0 | 8/12 | 12/12 |
| DS17-027 | native | 2/2 | 0 | 3/3 | 0 | 18/18 | 12/12 |
| DS17-027 | zero | 2/2 | 0 | 2/3 | 0 | 12/12 | 12/12 |
| DS17-031 | native | 2/2 | 0 | 3/3 | 0 | 18/18 | 12/12 |
| DS17-031 | zero | 2/2 | 0 | 3/3 | 0 | 18/18 | 12/12 |
| DS18-013 | native | 2/2 | 0 | 3/3 | 0 | 18/18 | 12/12 |
| DS18-013 | zero | 2/2 | 0 | 3/3 | 0 | 18/18 | 12/12 |
| DS18-023 | native | 2/2 | 0 | 3/3 | 0 | 18/18 | 12/12 |
| DS18-023 | zero | 2/2 | 0 | 3/3 | 0 | 18/18 | 12/12 |
| DS18-024 | native | 2/2 | 0 | 3/3 | 0 | 18/18 | 12/12 |
| DS18-024 | zero | 2/2 | 0 | 3/3 | 0 | 16/18 | 12/12 |
| DS18-029 | native | 2/2 | 0 | 3/3 | 0 | 18/18 | 12/12 |
| DS18-029 | zero | 2/2 | 0 | 3/3 | 0 | 18/18 | 12/12 |

Counts describe recorded attempts, not all possible starts. Missing terminal regions are unavailable, never assumed to have zero attempts. Partial stage receipts remain in the summary even when terminal counts are unavailable.

Recorded phase invocation costs:

| Member | Search seconds | Native seconds | Zero-led seconds | Recorded sum seconds | Unknown phases |
|---|---:|---:|---:|---:|---:|
| DS16-020 | 817.585 | 151.111 | 153.908 | 1122.603 | 0 |
| DS16-024 | 800.444 | 121.432 | 94.512 | 1016.388 | 0 |
| DS16-054 | 1672.474 | 69.561 | 65.738 | 1807.773 | 0 |
| DS16-058 | 1707.673 | 56.966 | 57.470 | 1822.109 | 0 |
| DS17-006 | 463.688 | 50.413 | 37.632 | 551.733 | 0 |
| DS17-015 | 783.527 | 91.470 | 92.962 | 967.959 | 0 |
| DS17-027 | 650.897 | 48.220 | 38.108 | 737.225 | 0 |
| DS17-031 | 567.133 | 58.399 | 58.400 | 683.932 | 0 |
| DS18-013 | 716.993 | 68.694 | 71.222 | 856.909 | 0 |
| DS18-023 | 628.758 | 59.961 | 59.699 | 748.418 | 0 |
| DS18-024 | 622.864 | 63.039 | 71.696 | 757.599 | 0 |
| DS18-029 | 648.189 | 60.885 | 60.802 | 769.876 | 0 |

Recorded sums omit unknown phases; they are not imputed zero. These are summed invocation times, not controller wall time or an embedded-speed benchmark. Shared bootstrap work is counted in the search phase.

Failure and qualification reasons:

| Member | Phase / stage | Status or reason |
|---|---|---|
| DS16-020 | native//result/diagnostics/terminal | {"converged": false, "evaluations": 363, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.0010058412012238574, "stop_reason": "nonstationary-solver-status-8"} |
| DS16-020 | native//result/diagnostics/best_feasible | {"converged": false, "evaluations": 25, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.0018843068649874815, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-020 | native//result/diagnostics/terminal | {"converged": false, "evaluations": 25, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.001884277469378602, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-020 | native//result/handoff/discovery_audit | {"payload_path": "/result/handoff/discovery_audit", "qualified": false, "stationarity": 0.005058657936181987} |
| DS16-020 | native//result/handoff/fitted_audit | {"payload_path": "/result/handoff/fitted_audit", "qualified": false, "stationarity": 0.005058657936181987} |
| DS16-020 | native//result/handoff/original | {"converged": false, "evaluations": 217, "payload_path": "/result/handoff/original", "stationarity": 0.005058657936181987, "stop_reason": "optimizer-success-returned-state-nonstationary"} |
| DS16-020 | native//result/diagnostics/best_feasible | {"converged": false, "evaluations": 246, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.0012015318709522327, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-020 | native//result/diagnostics/terminal | {"converged": false, "evaluations": 246, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.0012015309026081195, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-020 | native//result/diagnostics/best_feasible | {"converged": false, "evaluations": 46, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.003197674799565453, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-020 | native//result/diagnostics/terminal | {"converged": false, "evaluations": 46, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.003197593294204805, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-020 | native//result/fit | {"converged": false, "evaluations": 46, "payload_path": "/result/fit", "stationarity": 0.003197674799565453, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-020 | native//result/diagnostics/best_feasible | {"converged": false, "evaluations": 347, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.015111172152258899, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-020 | native//result/diagnostics/terminal | {"converged": false, "evaluations": 347, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.015111347770536548, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-020 | native//result/fit | {"converged": false, "evaluations": 347, "payload_path": "/result/fit", "stationarity": 0.015111172152258899, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-020 | zero//result/diagnostics/best_feasible | {"converged": false, "evaluations": 128, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.0016227959544578563, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-020 | zero//result/diagnostics/terminal | {"converged": false, "evaluations": 128, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.0016227959544578563, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-020 | zero//result/handoff/fitted_audit | {"payload_path": "/result/handoff/fitted_audit", "qualified": false, "stationarity": 395.691355598907} |
| DS16-020 | zero//result/handoff/fitted_audit | {"payload_path": "/result/handoff/fitted_audit", "qualified": false, "stationarity": 870.162785632116} |
| DS16-020 | zero//result/diagnostics/best_feasible | {"converged": false, "evaluations": 260, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.0015141541321847252, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-020 | zero//result/diagnostics/terminal | {"converged": false, "evaluations": 260, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.0015141541321847252, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-020 | zero//result/handoff/fitted_audit | {"payload_path": "/result/handoff/fitted_audit", "qualified": false, "stationarity": 498.0401706640327} |
| DS16-020 | zero//result/handoff/nonlinear/audit | {"payload_path": "/result/handoff/nonlinear/audit", "qualified": false, "stationarity": 0.00459110648679939} |
| DS16-020 | zero//result/handoff/nonlinear/fit | {"converged": false, "evaluations": 281, "payload_path": "/result/handoff/nonlinear/fit", "stationarity": 0.00459110648679939, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-020 | zero//result/handoff/nonlinear/solver/best_feasible | {"converged": false, "evaluations": 281, "payload_path": "/result/handoff/nonlinear/solver/best_feasible", "stationarity": 0.00459110648679939, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-020 | zero//result/handoff/nonlinear/solver/terminal | {"converged": false, "evaluations": 281, "payload_path": "/result/handoff/nonlinear/solver/terminal", "stationarity": 0.00459110648679939, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-020 | zero//result/diagnostics/best_feasible | {"converged": false, "evaluations": 23, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.0021048734093571664, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-020 | zero//result/diagnostics/terminal | {"converged": false, "evaluations": 23, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.0021048786362736216, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-020 | zero//result/diagnostics/best_feasible | {"converged": false, "evaluations": 26, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.0030142103837533796, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-020 | zero//result/diagnostics/terminal | {"converged": false, "evaluations": 26, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.003014211942456768, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-020 | zero//result/diagnostics/best_feasible | {"converged": false, "evaluations": 294, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.0010184019549336963, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-020 | zero//result/diagnostics/terminal | {"converged": false, "evaluations": 294, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.0010184019549336963, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-024 | native//result/handoff/discovery_audit | {"payload_path": "/result/handoff/discovery_audit", "qualified": false, "stationarity": 0.001462414863690073} |
| DS16-024 | native//result/handoff/fitted_audit | {"payload_path": "/result/handoff/fitted_audit", "qualified": false, "stationarity": 0.001462414863690073} |
| DS16-024 | native//result/handoff/original | {"converged": false, "evaluations": 134, "payload_path": "/result/handoff/original", "stationarity": 0.001462414863690073, "stop_reason": "optimizer-success-returned-state-nonstationary"} |
| DS16-024 | native//result/diagnostics/best_feasible | {"converged": false, "evaluations": 11, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.0059868898419902505, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-024 | native//result/diagnostics/terminal | {"converged": false, "evaluations": 11, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.0059868898419902505, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-024 | native//result/diagnostics/best_feasible | {"converged": false, "evaluations": 246, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.0019604004460158364, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-024 | native//result/diagnostics/terminal | {"converged": false, "evaluations": 246, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.0019604004460158364, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-024 | native//result/diagnostics/best_feasible | {"converged": false, "evaluations": 249, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.0011802419844235829, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-024 | native//result/diagnostics/terminal | {"converged": false, "evaluations": 249, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.0011802419844235829, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-024 | zero//result/diagnostics/best_feasible | {"converged": false, "evaluations": 507, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.01011661749112136, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-024 | zero//result/diagnostics/terminal | {"converged": false, "evaluations": 507, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.01011661749112136, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-024 | zero//result/fit | {"converged": false, "evaluations": 507, "payload_path": "/result/fit", "stationarity": 0.01011661749112136, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-024 | zero//result/diagnostics/best_feasible | {"converged": false, "evaluations": 321, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.0013921121228936454, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-024 | zero//result/diagnostics/terminal | {"converged": false, "evaluations": 321, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.0013921121228936454, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-024 | zero//result/handoff/fitted_audit | {"payload_path": "/result/handoff/fitted_audit", "qualified": false, "stationarity": 293.2282057460878} |
| DS16-024 | zero//result/diagnostics/best_feasible | {"converged": false, "evaluations": 210, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.0015040629012874464, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-024 | zero//result/diagnostics/terminal | {"converged": false, "evaluations": 210, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.0015040627926987465, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-024 | zero//result/handoff/fitted_audit | {"payload_path": "/result/handoff/fitted_audit", "qualified": false, "stationarity": 317.04632773580937} |
| DS16-024 | zero//result/diagnostics/best_feasible | {"converged": false, "evaluations": 476, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 2990.7932189116077, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-024 | zero//result/handoff/fitted_audit | {"payload_path": "/result/handoff/fitted_audit", "qualified": false, "stationarity": 155.72038281849058} |
| DS16-054 | native//result/diagnostics/best_feasible | {"converged": false, "evaluations": 15, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.004126816911667093, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-054 | native//result/diagnostics/terminal | {"converged": false, "evaluations": 15, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.004126816911667093, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-054 | native//result/diagnostics/best_feasible | {"converged": false, "evaluations": 458, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.005897628419326395, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-054 | native//result/diagnostics/terminal | {"converged": false, "evaluations": 458, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.005897628419326395, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-054 | native//result/fit | {"converged": false, "evaluations": 458, "payload_path": "/result/fit", "stationarity": 0.005897628419326395, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-054 | native//result/diagnostics/best_feasible | {"converged": false, "evaluations": 26, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.0010054452528975005, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-054 | native//result/diagnostics/terminal | {"converged": false, "evaluations": 26, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.0010054421916377287, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-054 | native//result/diagnostics/best_feasible | {"converged": false, "evaluations": 395, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.00821144615209235, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-054 | native//result/diagnostics/terminal | {"converged": false, "evaluations": 395, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.00821144615209235, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-054 | native//result/fit | {"converged": false, "evaluations": 395, "payload_path": "/result/fit", "stationarity": 0.00821144615209235, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-054 | native//result/diagnostics/best_feasible | {"converged": false, "evaluations": 24, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.006830947820617439, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-054 | native//result/diagnostics/terminal | {"converged": false, "evaluations": 24, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.006830947820617439, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-054 | native//result/fit | {"converged": false, "evaluations": 24, "payload_path": "/result/fit", "stationarity": 0.006830947820617439, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-054 | native//result/diagnostics/best_feasible | {"converged": false, "evaluations": 97, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.005563753892680268, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-054 | native//result/diagnostics/terminal | {"converged": false, "evaluations": 97, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.005563753892680268, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-054 | native//result/fit | {"converged": false, "evaluations": 97, "payload_path": "/result/fit", "stationarity": 0.005563753892680268, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-054 | zero//result/diagnostics/best_feasible | {"converged": false, "evaluations": 16, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.002432839451574617, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-054 | zero//result/diagnostics/terminal | {"converged": false, "evaluations": 16, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.002432839451574617, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-054 | zero//result/diagnostics/best_feasible | {"converged": false, "evaluations": 22, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.0015824585463667003, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-054 | zero//result/diagnostics/terminal | {"converged": false, "evaluations": 22, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.001582457053636091, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-054 | zero//result/diagnostics/best_feasible | {"converged": false, "evaluations": 33, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.0031364886637553074, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-054 | zero//result/diagnostics/terminal | {"converged": false, "evaluations": 33, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.003136486918786374, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-054 | zero//result/diagnostics/best_feasible | {"converged": false, "evaluations": 258, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.00105901809097925, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-054 | zero//result/diagnostics/terminal | {"converged": false, "evaluations": 258, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.0010590180597425084, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-054 | zero//result/handoff/fitted_audit | {"payload_path": "/result/handoff/fitted_audit", "qualified": false, "stationarity": 19.835384698814345} |
| DS16-054 | zero//result/handoff/fitted_audit | {"payload_path": "/result/handoff/fitted_audit", "qualified": false, "stationarity": 35.30886971219696} |
| DS16-054 | zero//result/handoff/nonlinear/solver/best_feasible | {"converged": false, "evaluations": 114, "payload_path": "/result/handoff/nonlinear/solver/best_feasible", "stationarity": 0.004442350047853594, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-054 | zero//result/handoff/nonlinear/solver/terminal | {"converged": false, "evaluations": 114, "payload_path": "/result/handoff/nonlinear/solver/terminal", "stationarity": 0.004442349067165952, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-054 | zero//result/handoff/fitted_audit | {"payload_path": "/result/handoff/fitted_audit", "qualified": false, "stationarity": 30.842100765918605} |
| DS16-058 | native//result/diagnostics/best_feasible | {"converged": false, "evaluations": 359, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 4186.6696068141255, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-058 | native//result/diagnostics/terminal | {"converged": false, "evaluations": 359, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.004707071593033671, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-058 | native//result/fit | {"converged": false, "evaluations": 359, "payload_path": "/result/fit", "stationarity": 4186.6696068141255, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-058 | native//result/diagnostics/best_feasible | {"converged": false, "evaluations": 16, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.0016530751860727817, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-058 | native//result/diagnostics/terminal | {"converged": false, "evaluations": 16, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.0016530751860727817, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-058 | zero//result/handoff/fitted_audit | {"payload_path": "/result/handoff/fitted_audit", "qualified": false, "stationarity": 437.31041363934554} |
| DS16-058 | zero//result/diagnostics/best_feasible | {"converged": false, "evaluations": 245, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.0011873314155446991, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-058 | zero//result/diagnostics/terminal | {"converged": false, "evaluations": 245, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.0011873314155446991, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-058 | zero//result/diagnostics/best_feasible | {"converged": false, "evaluations": 364, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 6501.6719646509655, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-058 | zero//result/handoff/fitted_audit | {"payload_path": "/result/handoff/fitted_audit", "qualified": false, "stationarity": 660.4131339407286} |
| DS16-058 | zero//result/handoff/fitted_audit | {"payload_path": "/result/handoff/fitted_audit", "qualified": false, "stationarity": 447.50270421521077} |
| DS16-058 | zero//result/diagnostics/best_feasible | {"converged": false, "evaluations": 24, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.0068556349387545665, "stop_reason": "nonstationary-solver-status-0"} |
| DS16-058 | zero//result/diagnostics/terminal | {"converged": false, "evaluations": 24, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.006855632393834448, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-006 | native//result/diagnostics/best_feasible | {"converged": false, "evaluations": 27, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.002990724573300657, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-006 | native//result/diagnostics/terminal | {"converged": false, "evaluations": 27, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.002990724573300657, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-006 | native//result/diagnostics/best_feasible | {"converged": false, "evaluations": 186, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.001067728112006179, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-006 | native//result/diagnostics/terminal | {"converged": false, "evaluations": 186, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.001067728112006179, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-006 | native//result/diagnostics/best_feasible | {"converged": false, "evaluations": 31, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.0022828791622170747, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-006 | native//result/diagnostics/terminal | {"converged": false, "evaluations": 31, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.0022828730460828367, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-006 | native//result/diagnostics/best_feasible | {"converged": false, "evaluations": 349, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 12041.950483595841, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-006 | native//result/diagnostics/best_feasible | {"converged": false, "evaluations": 237, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.004964231874859032, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-006 | native//result/diagnostics/terminal | {"converged": false, "evaluations": 237, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.004964231874859032, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-006 | native//result/diagnostics/best_feasible | {"converged": false, "evaluations": 301, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.001219546624193978, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-006 | native//result/diagnostics/terminal | {"converged": false, "evaluations": 301, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.001219546624193978, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-006 | native//result/diagnostics/best_feasible | {"converged": false, "evaluations": 17, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.0018574778217430449, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-006 | native//result/diagnostics/terminal | {"converged": false, "evaluations": 17, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.0018574709527233862, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-006 | zero//result/diagnostics/best_feasible | {"converged": false, "evaluations": 17, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.002812002739390751, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-006 | zero//result/diagnostics/terminal | {"converged": false, "evaluations": 17, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.0028120043458629285, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-006 | zero//result/handoff/fitted_audit | {"payload_path": "/result/handoff/fitted_audit", "qualified": false, "stationarity": 473.4578166220696} |
| DS17-006 | zero//result/handoff/fitted_audit | {"payload_path": "/result/handoff/fitted_audit", "qualified": false, "stationarity": 646.5144965177128} |
| DS17-006 | zero//result/handoff/discovery_audit | {"payload_path": "/result/handoff/discovery_audit", "qualified": false, "stationarity": 0.0013216694684525798} |
| DS17-006 | zero//result/handoff/fitted_audit | {"payload_path": "/result/handoff/fitted_audit", "qualified": false, "stationarity": 504.8907867020902} |
| DS17-006 | zero//result/handoff/original | {"converged": false, "evaluations": 143, "payload_path": "/result/handoff/original", "stationarity": 0.0013216694684525798, "stop_reason": "optimizer-success-returned-state-nonstationary"} |
| DS17-015 | native//result/diagnostics/best_feasible | {"converged": false, "evaluations": 310, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.0013473383671127395, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-015 | native//result/diagnostics/terminal | {"converged": false, "evaluations": 310, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.0013473383671127395, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-015 | zero//result/diagnostics/best_feasible | {"converged": false, "evaluations": 225, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.0027885778436092246, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-015 | zero//result/diagnostics/terminal | {"converged": false, "evaluations": 225, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.0027885778946261652, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-015 | zero//result/diagnostics/best_feasible | {"converged": false, "evaluations": 1, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.004522210654428704, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-015 | zero//result/diagnostics/terminal | {"converged": false, "evaluations": 1, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.004522210654428704, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-015 | zero//result/fit | {"converged": false, "evaluations": 1, "payload_path": "/result/fit", "stationarity": 0.004522210654428704, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-015 | zero//result/diagnostics/best_feasible | {"converged": false, "evaluations": 148, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.007152212973878136, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-015 | zero//result/diagnostics/terminal | {"converged": false, "evaluations": 148, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.007152212973878136, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-015 | zero//result/fit | {"converged": false, "evaluations": 148, "payload_path": "/result/fit", "stationarity": 0.007152212973878136, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-015 | zero//result/diagnostics/best_feasible | {"converged": false, "evaluations": 481, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.01034228377559998, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-015 | zero//result/diagnostics/terminal | {"converged": false, "evaluations": 481, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.01034228377559998, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-015 | zero//result/fit | {"converged": false, "evaluations": 481, "payload_path": "/result/fit", "stationarity": 0.01034228377559998, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-015 | zero//result/handoff/fitted_audit | {"payload_path": "/result/handoff/fitted_audit", "qualified": false, "stationarity": 488.9433127892316} |
| DS17-015 | zero//result/handoff/fitted_audit | {"payload_path": "/result/handoff/fitted_audit", "qualified": false, "stationarity": 281.5384735581393} |
| DS17-015 | zero//result/handoff/discovery_audit | {"payload_path": "/result/handoff/discovery_audit", "qualified": false, "stationarity": 0.0010243060775137203} |
| DS17-015 | zero//result/handoff/fitted_audit | {"payload_path": "/result/handoff/fitted_audit", "qualified": false, "stationarity": 494.38004444576416} |
| DS17-015 | zero//result/handoff/original | {"converged": false, "evaluations": 235, "payload_path": "/result/handoff/original", "stationarity": 0.0010243060775137203, "stop_reason": "optimizer-success-returned-state-nonstationary"} |
| DS17-015 | zero//result/diagnostics/best_feasible | {"converged": false, "evaluations": 556, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.004526320922437321, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-015 | zero//result/diagnostics/terminal | {"converged": false, "evaluations": 556, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.004526320922437321, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-015 | zero//result/fit | {"converged": false, "evaluations": 556, "payload_path": "/result/fit", "stationarity": 0.004526320922437321, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-027 | native//result/diagnostics/best_feasible | {"converged": false, "evaluations": 130, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.0017022996607961817, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-027 | native//result/diagnostics/terminal | {"converged": false, "evaluations": 130, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.0017022996607961817, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-027 | native//result/diagnostics/best_feasible | {"converged": false, "evaluations": 23, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.009590796452348296, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-027 | native//result/diagnostics/terminal | {"converged": false, "evaluations": 23, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.009590796452348296, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-027 | native//result/diagnostics/best_feasible | {"converged": false, "evaluations": 278, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.0014675780178171572, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-027 | native//result/diagnostics/terminal | {"converged": false, "evaluations": 278, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.0014675780059385437, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-027 | native//result/diagnostics/best_feasible | {"converged": false, "evaluations": 340, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 5125.333699258689, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-027 | native//result/diagnostics/terminal | {"converged": false, "evaluations": 340, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.0015540207873302597, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-027 | zero//result/handoff/fitted_audit | {"payload_path": "/result/handoff/fitted_audit", "qualified": false, "stationarity": 433.3730387481403} |
| DS17-027 | zero//result/handoff/discovery_audit | {"payload_path": "/result/handoff/discovery_audit", "qualified": false, "stationarity": 0.001773898802822943} |
| DS17-027 | zero//result/handoff/fitted_audit | {"payload_path": "/result/handoff/fitted_audit", "qualified": false, "stationarity": 359.17576957562767} |
| DS17-027 | zero//result/handoff/original | {"converged": false, "evaluations": 234, "payload_path": "/result/handoff/original", "stationarity": 0.001773898802822943, "stop_reason": "optimizer-success-returned-state-nonstationary"} |
| DS17-027 | zero//result/diagnostics/best_feasible | {"converged": false, "evaluations": 14, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.001573656520705985, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-027 | zero//result/diagnostics/terminal | {"converged": false, "evaluations": 14, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.001573656520705985, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-027 | zero//result/diagnostics/best_feasible | {"converged": false, "evaluations": 182, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.0023916101971789144, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-027 | zero//result/diagnostics/terminal | {"converged": false, "evaluations": 182, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.0023917192334183615, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-027 | zero//result/handoff/fitted_audit | {"payload_path": "/result/handoff/fitted_audit", "qualified": false, "stationarity": 201.72960003646972} |
| DS17-027 | zero//result/diagnostics/best_feasible | {"converged": false, "evaluations": 330, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.0010489825351323936, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-027 | zero//result/diagnostics/terminal | {"converged": false, "evaluations": 330, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.0010489825351323936, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-031 | native//result/diagnostics/best_feasible | {"converged": false, "evaluations": 23, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.00204325267514685, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-031 | native//result/diagnostics/terminal | {"converged": false, "evaluations": 23, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.00204325267514685, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-031 | native//result/diagnostics/best_feasible | {"converged": false, "evaluations": 315, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 4639.532415563326, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-031 | native//result/diagnostics/best_feasible | {"converged": false, "evaluations": 192, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.0011968579590520972, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-031 | native//result/diagnostics/terminal | {"converged": false, "evaluations": 192, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.0011968579590520972, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-031 | native//result/diagnostics/best_feasible | {"converged": false, "evaluations": 320, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 4238.061208617359, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-031 | zero//result/handoff/fitted_audit | {"payload_path": "/result/handoff/fitted_audit", "qualified": false, "stationarity": 232.91763434275953} |
| DS17-031 | zero//result/diagnostics/best_feasible | {"converged": false, "evaluations": 43, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.002310591720057359, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-031 | zero//result/diagnostics/terminal | {"converged": false, "evaluations": 43, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.002310591720057359, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-031 | zero//result/diagnostics/best_feasible | {"converged": false, "evaluations": 333, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.001332460625252399, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-031 | zero//result/diagnostics/terminal | {"converged": false, "evaluations": 333, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.001332460625252399, "stop_reason": "nonstationary-solver-status-0"} |
| DS17-031 | zero//result/handoff/fitted_audit | {"payload_path": "/result/handoff/fitted_audit", "qualified": false, "stationarity": 431.3420660290676} |
| DS17-031 | zero//result/handoff/fitted_audit | {"payload_path": "/result/handoff/fitted_audit", "qualified": false, "stationarity": 614.4503314530789} |
| DS18-013 | native//result/diagnostics/best_feasible | {"converged": false, "evaluations": 379, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.001935718562487107, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-013 | native//result/diagnostics/terminal | {"converged": false, "evaluations": 379, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.001935718562487049, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-013 | native//result/diagnostics/best_feasible | {"converged": false, "evaluations": 212, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.001071228714460165, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-013 | native//result/diagnostics/terminal | {"converged": false, "evaluations": 212, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.001071228714460165, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-013 | native//result/diagnostics/best_feasible | {"converged": false, "evaluations": 284, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.001986742187428031, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-013 | native//result/diagnostics/terminal | {"converged": false, "evaluations": 284, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.0019867420322761398, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-013 | zero//result/diagnostics/best_feasible | {"converged": false, "evaluations": 243, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.0010038428529643983, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-013 | zero//result/diagnostics/terminal | {"converged": false, "evaluations": 243, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.0010038428529643983, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-013 | zero//result/handoff/fitted_audit | {"payload_path": "/result/handoff/fitted_audit", "qualified": false, "stationarity": 8.14900746418488} |
| DS18-013 | zero//result/diagnostics/best_feasible | {"converged": false, "evaluations": 389, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.0016325305401201362, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-013 | zero//result/diagnostics/terminal | {"converged": false, "evaluations": 389, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.0016325305401201362, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-013 | zero//result/diagnostics/best_feasible | {"converged": false, "evaluations": 28, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.0016418955081514142, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-013 | zero//result/diagnostics/terminal | {"converged": false, "evaluations": 28, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.0016418955081514142, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-013 | zero//result/handoff/fitted_audit | {"payload_path": "/result/handoff/fitted_audit", "qualified": false, "stationarity": 81.53690631839365} |
| DS18-013 | zero//result/diagnostics/best_feasible | {"converged": false, "evaluations": 557, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.06015535064980009, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-013 | zero//result/diagnostics/terminal | {"converged": false, "evaluations": 557, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.06015534261627411, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-013 | zero//result/diagnostics/best_feasible | {"converged": false, "evaluations": 25, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.0021179899775116695, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-013 | zero//result/diagnostics/terminal | {"converged": false, "evaluations": 25, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.0021180105802312, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-013 | zero//result/handoff/fitted_audit | {"payload_path": "/result/handoff/fitted_audit", "qualified": false, "stationarity": 144.75343278976845} |
| DS18-023 | native//result/diagnostics/best_feasible | {"converged": false, "evaluations": 24, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.0014564221577680302, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-023 | native//result/diagnostics/terminal | {"converged": false, "evaluations": 24, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.0014564209770697757, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-023 | zero//result/handoff/fitted_audit | {"payload_path": "/result/handoff/fitted_audit", "qualified": false, "stationarity": 230.04088190510407} |
| DS18-023 | zero//result/diagnostics/best_feasible | {"converged": false, "evaluations": 369, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.001354885432057554, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-023 | zero//result/diagnostics/terminal | {"converged": false, "evaluations": 369, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.0013548854322960832, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-023 | zero//result/diagnostics/best_feasible | {"converged": false, "evaluations": 18, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.0013659919840400409, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-023 | zero//result/diagnostics/terminal | {"converged": false, "evaluations": 18, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.0013660264398744626, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-023 | zero//result/diagnostics/best_feasible | {"converged": false, "evaluations": 247, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.001048089060891883, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-023 | zero//result/diagnostics/terminal | {"converged": false, "evaluations": 247, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.001048089060891883, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-023 | zero//result/handoff/fitted_audit | {"payload_path": "/result/handoff/fitted_audit", "qualified": false, "stationarity": 310.13066481389296} |
| DS18-023 | zero//result/diagnostics/best_feasible | {"converged": false, "evaluations": 129, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.0013860541333723664, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-023 | zero//result/diagnostics/terminal | {"converged": false, "evaluations": 129, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.0013860541566213247, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-023 | zero//result/handoff/fitted_audit | {"payload_path": "/result/handoff/fitted_audit", "qualified": false, "stationarity": 149.724302155177} |
| DS18-024 | native//result/diagnostics/best_feasible | {"converged": false, "evaluations": 235, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.0020201828425120277, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-024 | native//result/diagnostics/terminal | {"converged": false, "evaluations": 235, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.0020203322927709044, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-024 | native//result/diagnostics/best_feasible | {"converged": false, "evaluations": 23, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.0013363085072175649, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-024 | native//result/diagnostics/terminal | {"converged": false, "evaluations": 23, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.0013363085512743608, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-024 | zero//result/diagnostics/best_feasible | {"converged": false, "evaluations": 18, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.00146438283515827, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-024 | zero//result/diagnostics/terminal | {"converged": false, "evaluations": 18, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.00146438283515827, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-024 | zero//result/diagnostics/best_feasible | {"converged": false, "evaluations": 164, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.00462019945256216, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-024 | zero//result/diagnostics/terminal | {"converged": false, "evaluations": 164, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.00462019945256216, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-024 | zero//result/diagnostics/best_feasible | {"converged": false, "evaluations": 500, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 2856.9576605346765, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-024 | zero//result/handoff/fitted_audit | {"payload_path": "/result/handoff/fitted_audit", "qualified": false, "stationarity": 381.4782998709714} |
| DS18-024 | zero//result/diagnostics/best_feasible | {"converged": false, "evaluations": 278, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.0038284526679325387, "stop_reason": "nonstationary-solver-status-8"} |
| DS18-024 | zero//result/fit | {"converged": false, "evaluations": 278, "payload_path": "/result/fit", "stationarity": 0.0038284526679325387, "stop_reason": "nonstationary-solver-status-8"} |
| DS18-024 | zero//result/diagnostics/best_feasible | {"converged": false, "evaluations": 333, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.001430468847639671, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-024 | zero//result/diagnostics/terminal | {"converged": false, "evaluations": 333, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.001430468847639671, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-024 | zero//result/diagnostics/best_feasible | {"converged": false, "evaluations": 53, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 34.972726485388414, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-024 | zero//result/diagnostics/terminal | {"converged": false, "evaluations": 53, "payload_path": "/result/diagnostics/terminal", "stationarity": 34.972726485388414, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-024 | zero//result/fit | {"converged": false, "evaluations": 53, "payload_path": "/result/fit", "stationarity": 34.972726485388414, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-024 | zero//result/handoff/fitted_audit | {"payload_path": "/result/handoff/fitted_audit", "qualified": false, "stationarity": 362.59630686802484} |
| DS18-024 | zero//result/diagnostics/best_feasible | {"converged": false, "evaluations": 22, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.002138312685889869, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-024 | zero//result/diagnostics/terminal | {"converged": false, "evaluations": 22, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.002138312685889869, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-024 | zero//result/diagnostics/best_feasible | {"converged": false, "evaluations": 18, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.0032559588445479903, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-024 | zero//result/diagnostics/terminal | {"converged": false, "evaluations": 18, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.0032554027837079502, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-024 | zero//result/handoff/fitted_audit | {"payload_path": "/result/handoff/fitted_audit", "qualified": false, "stationarity": 286.4222917099644} |
| DS18-029 | native//result/diagnostics/best_feasible | {"converged": false, "evaluations": 25, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.0014199608843326705, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-029 | native//result/diagnostics/terminal | {"converged": false, "evaluations": 25, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.0014199609153594211, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-029 | native//result/diagnostics/best_feasible | {"converged": false, "evaluations": 17, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.0017632306861335009, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-029 | native//result/diagnostics/terminal | {"converged": false, "evaluations": 17, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.0017632305708156007, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-029 | zero//result/diagnostics/best_feasible | {"converged": false, "evaluations": 46, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.0015904187906104713, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-029 | zero//result/diagnostics/terminal | {"converged": false, "evaluations": 46, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.0015904187906104713, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-029 | zero//result/handoff/fitted_audit | {"payload_path": "/result/handoff/fitted_audit", "qualified": false, "stationarity": 31.40845245729718} |
| DS18-029 | zero//result/handoff/fitted_audit | {"payload_path": "/result/handoff/fitted_audit", "qualified": false, "stationarity": 72.80330391301185} |
| DS18-029 | zero//result/handoff/fitted_audit | {"payload_path": "/result/handoff/fitted_audit", "qualified": false, "stationarity": 92.26803239145232} |
| DS18-029 | zero//result/diagnostics/best_feasible | {"converged": false, "evaluations": 360, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.0017798783404008268, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-029 | zero//result/diagnostics/terminal | {"converged": false, "evaluations": 360, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.0017798778750559383, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-029 | zero//result/diagnostics/best_feasible | {"converged": false, "evaluations": 23, "payload_path": "/result/diagnostics/best_feasible", "stationarity": 0.003782319670140366, "stop_reason": "nonstationary-solver-status-0"} |
| DS18-029 | zero//result/diagnostics/terminal | {"converged": false, "evaluations": 23, "payload_path": "/result/diagnostics/terminal", "stationarity": 0.003782323049514008, "stop_reason": "nonstationary-solver-status-0"} |

Frequency fit remains separate from accuracy:

| Member | Arm | Native RMS Hz | Zero-led RMS Hz |
|---|---|---:|---:|
| DS16-020 | fitted-c | 74.504975 | 73.282418 |
| DS16-020 | zero-c | 147.700953 | 138.657900 |
| DS16-024 | fitted-c | 70.262200 | 59.335434 |
| DS16-024 | zero-c | 117.536787 | 114.009953 |
| DS16-054 | fitted-c | 55.160014 | 58.955477 |
| DS16-054 | zero-c | 56.600239 | 59.783660 |
| DS16-058 | fitted-c | 55.303625 | 55.303625 |
| DS16-058 | zero-c | 113.253542 | 113.253542 |
| DS17-006 | fitted-c | 61.831264 | 61.831263 |
| DS17-006 | zero-c | 134.027139 | 134.027139 |
| DS17-015 | fitted-c | 50.908550 | 53.510073 |
| DS17-015 | zero-c | 102.028795 | 103.299064 |
| DS17-027 | fitted-c | 75.899853 | 75.899853 |
| DS17-027 | zero-c | 116.068171 | 116.068171 |
| DS17-031 | fitted-c | 60.544486 | 60.544486 |
| DS17-031 | zero-c | 117.234445 | 117.234446 |
| DS18-013 | fitted-c | 91.152454 | 91.558094 |
| DS18-013 | zero-c | 93.681827 | 94.455472 |
| DS18-023 | fitted-c | 88.404339 | 88.404339 |
| DS18-023 | zero-c | 99.477042 | 99.477042 |
| DS18-024 | fitted-c | 56.225199 | 56.225199 |
| DS18-024 | zero-c | 88.028021 | 88.028022 |
| DS18-029 | fitted-c | 58.628401 | 65.669440 |
| DS18-029 | zero-c | 60.091033 | 67.164593 |

Failure reasons, regional qualification counts, intermediate joint attempts, partial stage/claim coverage, invocation costs and receipt hashes are retained in [SUMMARY.json](SUMMARY.json). Unknown terminal regions are unavailable, not completed zero-attempt regions. The progression screen is a consumed pilot decision receipt, not deployment authorization.

Raw receipts remain local. Published byte hashes identify retained evidence; this is not a remote standalone replay bundle. See [publication scope](PUBLICATION_POLICY.md).

The [runtime audit](ENVIRONMENT_AUDIT.md) records one shard's interpreter-path deviation, and the [host observations](HOST_IO_OBSERVATION.md) document I/O contention included in timed budgets. The [handoff analysis](HANDOFF_OBSERVATIONS.md) explains why this comparison includes conditional repair opportunities as well as discovery differences; it does not isolate the grid alone.
