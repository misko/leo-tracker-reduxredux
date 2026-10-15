# C059 clock endpoint: genuine residual gradients at numerical stopping scale

The unchanged training-best rejected clock endpoint replays **J46116.275400, NLL45544.247167 and original-scale KKT0.008057196**. Its score remains1075.561155 below the accepted clock selector, but the endpoint is still nonstationary and ineligible. The derivative audit completed **58 objective evaluations,58 explicit native predictions and zero fits** in52.327seconds.

The dominant acceptance failure is a group-calibration derivative, not an observed visibility discontinuity:

| Original-chart direction | Analytic derivative | Central FD at1e-5 | Gradient-derived curvature | Estimated coordinate decrease / objective ULP |
|---|---:|---:|---:|---:|
| Group coordinate100 | +0.008057196 | +0.008059578 | 491806.467 | 9.071 |
| Free satellite timing coordinate14 | −0.001670868 | −0.001674198 | 84870.576 | 2.261 |
| Receiver RF coordinate6 | +0.000278489 | +0.000278669 | 1700.548 | 3.134 |
| Common-clock coordinate82 | −0.000035102 | −0.000036744 | 7.371391 | 11.487 |

The objective's floating-point spacing is7.27596×10⁻¹². For the group direction, the estimated one-coordinate quadratic improvement is6.60×10⁻¹¹. Curvature is stable between1e-5 and1e-6 steps. Value-based finite differences become noisy at the smallest steps because the absolute objective changes are tiny; the derivative and curvature evidence supports a real small residual rather than accepting the solver-success flag as stationarity. These are coordinate estimates, **not** a full Hessian, positive-definiteness certificate or proof of a successful Newton update.

The largest raw timing derivative,−441.567061, occurs on an active +20second satellite timing bound (constraint88). Its downhill direction points outside the original feasible region and is correctly removed by the constrained KKT calculation. Three outward probe sides were infeasible and were skipped without projection. The remaining free timing residual is reported separately above; the large active-bound derivative must not be misdiagnosed as a441-unit stationarity error.

Across all57 feasible side probes there were **zero native visibility changes and zero temporal-support changes**. Larger timing probes cross a few ephemeris interpolation cells; the1e-5 free-timing probe used in the table stays within its cells. Neither group nor clock probes alter visibility or interpolation cells. This narrows the explanation to numerical stopping/conditioning at this endpoint; it does not diagnose every broader-search failure or prove a globally correct basin.

## Preserved admission failure

Frozen v1 stopped before any objective or orbit call because it incorrectly demanded a fresh optimizer initializer instead of a diagnostic chart at a saved endpoint. V2 constructs the same original constraint/matrix/scale objects while retaining the exact raw endpoint for every evaluation. It records the constructor's proposed9.99979×10⁻¹⁰second timing margin but **does not apply it**. Raw constraint minimum is2.13×10⁻¹⁴; chart reconstruction error is1.07×10⁻¹⁴. Original feasibility, objective/NLL and KKT all replay. No acceptance tolerance changed, and v1 remains pinned as a separate zero-objective failed attempt.

Source **87fbbd481**, four component tests and Ruff passed, including a real native-clock timing-bound fixture that the old initializer guard rejects while the diagnostic chart preserves exactly. Original v1 source iscfb31673e. Namespace:`/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-c059-clock-endpoint-audit-v2`; result SHA256:**7ec5add5caa4e43e3e7999ffc53b63207d50a9445e0d1d2faf61362f1be30394**. Independent external135/140second bounds were active. No reference, held or locked data was read.

A subsequent, separately specified matched endpoint-repeat versus active-tangent Newton control could test strict numerical completion while retaining the original clock incumbent. It would need exact-start treatment of the active timing face, a complete tangent Hessian certificate and the unchanged original KKT gate. No such fit was launched by this audit, and the poor full48 position results remain unchanged.
