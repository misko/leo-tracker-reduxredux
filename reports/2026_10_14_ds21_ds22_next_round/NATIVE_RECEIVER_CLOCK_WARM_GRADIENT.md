# Rejected warm endpoint has sub-ULP coordinate improvements

Nine objective/gradient evaluations, without fitting, support a numerical stopping explanation for the native-clock C001 warm endpoint. Its residual gradients are real: central differences broadly agree with the analytic derivatives. However, estimated improvements along the two tested feasible coordinates are smaller than one float64 spacing of the total objective. This is evidence for investigating gradient-based refinement, not permission to relax the 0.001 stationarity requirement or accept the rejected endpoint.

| Feasible optimizer coordinate | Analytic derivative | Central difference, step 1e-5 | Central difference, step 1e-6 | Directional curvature | Estimated quadratic decrease |
|---|---:|---:|---:|---:|---:|
| Physical timing coordinate 49 | 0.001636959 | 0.001637818 | 0.001637090 | 294474.46 | 4.550e-12 |
| Nuisance coordinate 18, first band offset | 0.002061475 | 0.002064917 | 0.002048182 | 394275.98 | 5.389e-12 |

The objective spacing is 7.275958e-12. Curvature estimated from analytic-gradient differences agrees across the two step sizes. The smaller-step nuisance objective difference shows expected cancellation sensitivity; it is not used to replace the analytic gradient. The original solver uses absolute `ftol=1e-11`, stopped after 12.225 seconds, and reported success while the independent stationarity requirement remained unmet.

The replayed physical stationarity is 0.001630410 and the scaled nuisance maximum is 0.002061475, reproducing the saved maximum. One timing constraint is active (index 70). The diagnostic selects the largest centrally feasible coordinate separately in physical and nuisance parameterizations; it does not move an active bound or assume every unconstrained direction is feasible. These two scalar curvature probes do not establish the full Hessian, total possible improvement, or convergence of a future refinement method.

No reference or held data was read, no optimizer was called, and the rejected fit remains unchanged. A future numerical prototype must start from the same original warm seed, count all gradient/Hessian work within a declared fitting budget, enforce the original bounds, and pass the unchanged full stationarity audit before any localization result is evaluated.

Source `600efc1f5`; two feasibility-selection tests and Ruff pass. Actual elapsed time 33.616338 seconds; nine objective evaluations and zero fits. Receipts: `local/ds22-native-clock-warm-gradient-v1`; report SHA256 `174b280df11fd0384c753fcf5e59d84652d6bcf525726bc8eac6b3f9cd1692d7`.
