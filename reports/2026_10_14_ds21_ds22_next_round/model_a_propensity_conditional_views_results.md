# A035/A053 propensity winners: conditional channel views and stopping audit

**A053: full 0.256462 km, CH1–4 0.190263 km, CH5–8 1.255084 km.** The full result remains slightly worse than the low view. A035 remains poor: full 9.004813 km and low 8.730501 km; its high-view fit fails strict stationarity and has no eligible accuracy result. These are conditional development views, **not independently trained half-only A pipelines**.

Each view starts from its own previously training-selected full-data q winner, preserving the complete physical vector, common-clock nuisance and propensity coefficients. Banks 55/59, full-derived calibration frame/clock nodes, frozen learned high shifts, priors, fitted-c freedom and original 25/50 km disks remain unchanged. Candidates and calibration already used both bands; fitting fewer rows does not remove that leakage. No held observations or new reference-selected seed were used.

New source `010e4b468` and four owned tests pass; nine tests including the prior release component and Ruff pass. Exact view qualification used **six objectives, zero fits**, in 7.920 seconds: two original full-state replays and four half views, verifying likelihood partition and identical row posteriors without seed projection.

Four independent original-fitter calls used **20 seconds / 600 iterations**, up to four single-thread workers, each with 90/105/110 second internal/TERM/KILL limits. Wave150 completed all units in **12.228 seconds**. Three endpoints passed unchanged independent strict KKT ≤0.001. Every original outcome sealed **before** configured-reference scoring: `4d8d9faa146b4b0272b1388d2ae3fd8906c09b44e6fb841c668c28024a95c5d2`.

| Case / view | Windows | Conditional NLL | Full KKT | Radius / disk km | Configured error km |
|---|---:|---:|---:|---:|---:|
| 035 full source | 2907 | 29928.951508 | 0.000097955 | 6.096 / 25 | 9.004813 |
| 035 CH1–4 | 1714 | 17853.172357 | 0.000791109 | 6.081 / 25 | 8.730501 |
| 035 CH5–8 | 1193 | 11415.915037 | **0.004184126** | 4.786 / 25 | unavailable |
| 053 full source | 1870 | 19175.013893 | 0.000389571 | 34.332 / 50 | 0.256462 |
| 053 CH1–4 | 1274 | 12927.917864 | 0.000032389 | 34.386 / 50 | **0.190263** |
| 053 CH5–8 | 596 | 6007.134241 | 0.000075054 | 33.375 / 50 | 1.255084 |

Do not compare total NLL across different row populations as one score. Per-band frequency improvements versus each full source's own band loss are recorded separately. A035's rejected high view reported solver success after 4.204 seconds; it was not a 20-second timeout. No failed outcome was retried or accepted with a relaxed threshold. Configured coordinates are not independently confirmed physical truth.

## Zero-fit audit of A035's excluded lower-objective common-start q state

The exact original rejected full outcome has J=28882.674102, KKT=0.002364824, solver success and elapsed 11.209 seconds. It remains excluded despite scoring below the accepted q winner J=30174.189041. A separately frozen read-only audit used **ten objectives and nine explicit orbital predictors, zero fits**, in 4.562 seconds. It selected the strongest centrally feasible physical and clock/q coordinate by training gradient only, with scaled central steps 1e−5 and 1e−6. Both probes retain visibility and orbital interpolation segments exactly.

| Direction | Analytic scaled gradient | Central FD at 1e−5 / 1e−6 | Gradient-derived curvature | Implied 1D improvement / objective ULP |
|---|---:|---:|---:|---:|
| Relative timing basis coordinate 54 | +0.002364824 | +0.002370143 / +0.002355591 | 152834.034 | 5.03 ULP |
| Propensity nuisance coordinate 37, scale 0.5 | −0.000048887 | −0.000049295 / −0.000049113 | 41.004969 | 8.01 ULP |

One objective ULP is **3.638e−12**. The timing coordinate's implied Newton displacement is only about **1.55e−8 seconds**, yet its gradient exceeds the strict threshold. Stable gradient differences and unchanged support favor a real remaining gradient with an objective-scale stopping limitation. They do not establish a positive coupled Hessian, global minimum, or improved geography. The strongest free propensity gradient already passes the threshold; timing drives the full KKT failure. This evidence motivates a new numerical control rather than threshold relaxation.

## Next bounded numerical control

The proposed small pilot uses both original rejected common q endpoints and matched accepted q winners for **035 and 053**. For each of these four saved complete endpoints, compare an original SLSQP repeat against a positive-tangent-Hessian Newton finish: **eight calls**, each with an explicit 20-second / 600 actual objective-evaluation budget, including Hessian probes and terminal replay. This is additional endpoint work, not a claim to solve the original search inside its earlier cost. Both arms share exact endpoint, model, learned contrast, bank and original disk; five prior CV failures and five full-release failures remain preserved.

Only the existing pure `tangent_gradient_finish.finish` port is reusable directly. The native wrapper's hard-coded 25 km constraints are not appropriate for A053. A new qualified adapter must retain actual disk/fixed-position options, exact active affine tangents, full projected KKT, positive curvature and feasibility, reject active curved disks, count all probes, and keep the ULP safeguard narrow. It must not seed geography from truth. All outcomes and training selectors seal before any new accuracy evaluation.

[Numeric states, likelihoods and audit provenance](model_a_propensity_conditional_views_results.json). Output: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-a-propensity-half-views-035053-v1`.
