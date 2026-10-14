# B059 rejected high profile: real derivatives near objective precision

The rejected high fixed-XY profile's residual derivative is real at the tested stable interpolation cells. Its strongest scaled timing derivative.008014186 agrees with objective finite differences; a one-coordinate quadratic correction predicts only39.012 objective ULPs improvement. The strongest centrally feasible nuisance direction predicts3.392ULPs. This supports qualifying the shared bounded numerical-finishing method before adding localization-model freedom. It does not establish that a coupled positive-Hessian correction will succeed or make the endpoint eligible.

Source/protocol `31431e414` passed seven owned tests and Ruff before freeze. The audit completed in16.860s including source checks/preparation:13 full probability-objective calls,13 separately counted explicit orbit/support predictor calls, zero optimizer/localization calls. Every objective's internal predictor is additional to the explicit support calls. No endpoint was updated, no source acceptance flag changed, and no reference/held/locked measurements were read. Source fit objective/NLL replay exactly; the original FIXED-XY KKT independently replays physical.008014185912/nuisance.003001634766. FREE geography derivatives do not enter this audit.

| Direction | Scaled analytic derivative | Central FD at1e-5 | Central FD at1e-6 | Derivative curvature | Implied coordinate decrease | Objective ULPs |
|---|---:|---:|---:|---:|---:|---:|
| physical coordinate36, relative timing basis |.008014186 |.008013194 |.008021743 |226272.573 |1.41924e-10 |39.012 |
| nuisance coordinate18, RX0 group offset, scale5000Hz |−.003001635 |−.002999514 |−.003003152 |365058.728 |1.23402e-11 |3.392 |

The objective is27757.97255617943, with one ULP3.637978807e-12. The physical coordinate's scale is1s; the offset probes at scaled1e-5/1e-6 are.05/.005Hz. At scaled1e-7, objective-FD derivatives are.007967174/−.003019522, while analytic-gradient curvature remains226272.564/365058.728. Increasing objective differencing error at smaller steps is consistent with cancellation; it does not warrant relaxing the unchanged KKT≤.001 requirement.

All thirteen evaluated points preserve visibility and ephemeris interpolation cells exactly. Thus no measured seam crossing explains these two derivatives. Both XY coordinates were fixed and never probed. The original25km donor disk is interior; the minimum physical constraint slack is6.503405470. Five active q bounds remain fixed/excluded from central coordinate probing. This is a two-coordinate audit, not a full tangent Hessian, minimum certificate, measurement-noise estimate, or proof that all coordinates are well behaved.

The original profile remains rejected. Its objective296.886201 below the old incumbent remains a material optimization lead, separate from calibration representability. The preceding three-call control's eligible training selector remains the low release1.210448km; the earlier all1.129758/low1.035045/high.468524km matched-view result remains unchanged. No retry/release was run here.

Output: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-b-fixed-profile-roundoff-059-v1`, one worker internal120/TERM135/KILL140. Terminal SHA256 `20fac0932fbe5829998743b9c41dda9898d94772f046c5af0a5378d045640e0a`; seal `17cedf9b99d7d2bb6448ef740bfe65eace3d3dcfdad0a38fc6b13a22b38f412a`.
