# B059 clock-basis comparison: RF scaling negative, band contrast partially helps

Replacing the existing common-clock columns with actual-RF-scaled columns does not represent the frozen half functions better: RMS113.886101→114.283480Hz. A common clock plus the existing regularized band-contrast clock lowers RMS to95.805755Hz with legal coefficients. This is a partial representability gain, not a localization result, hardware diagnosis or evidence to prefer a new clock likelihood. Numerical rejection of the lower-score high fixed-XY profile remains a separate unresolved lead.

Source/protocol `f1d63c871` passed four owned tests and Ruff before freeze. The one-worker diagnostic completed in15.172s including guards/preparation, with exactly eight numerical linear procedures (unconstrained SVD and legal-box BVLS for four arms), three original calibration-function calls, zero probability objectives, zero orbital predictors and zero localization fits. It rereads neither original held/locked measurements nor reference positions. Source functions replay their original designs, and the common projection reproduces the previous frozen result exactly.

All arms use the same2522 measured-row timestamps/RFs/receivers/groups and the same low/high correction-function splice, original baseline, five affine/RF columns and static group contrasts. The fractional replacement uses actual_RF/11.5846875GHz, the unchanged full-frame training RF center. This is a normalized fractional-frequency hypothesis, not proof of any physical LO or oscillator authority. The contrast columns, prior, scales and±2000Hz boxes come directly from existing `GroupCalibrationObjective(group_clock=True)`, with original null-space/gauge and training receiver high fractions.

| Design/solution | Data rank | Total RMS Hz | Low RMS Hz | High RMS Hz | Max abs Hz | Contrast prior penalty |
|---|---:|---:|---:|---:|---:|---:|
| common, unconstrained=bounded |25/25 |113.886101 |82.087443 |151.351970 |499.692906 |0 |
| fractional common, unconstrained=bounded |25/25 |114.283480 |82.609738 |151.675650 |512.347307 |0 |
| common+contrast, unpenalized unconstrained |43/43 |72.508399 |51.343628 |97.146920 |676.252420 |5343.914914 |
| common+contrast, unpenalized bounded |43/43 |74.653872 |51.457510 |101.183355 |676.752544 |2996.034792 |
| common+contrast, regularized unconstrained=bounded |43/43 |95.805755 |69.722632 |126.742418 |485.918253 |50.185189 |

The unpenalized contrast optimum violates one original coefficient lower bound:−3195.028Hz versus−2000Hz. Its bounded counterpart puts that coefficient at−2000Hz; BVLS status2, three iterations. The regularized solution is wholly interior with added coefficients−300.214..401.510Hz, so its bounded solution equals the unconstrained one (status3, zero iterations). Extra flexibility improves RMS but can worsen the largest row discrepancy, as the unpenalized maxima show.

Regularization minimizes SSE/125**2 + theta.T@P_original_clock@theta, penalizing ONLY added contrast coefficients in this diagnostic projection. The table's prior column is half that quadratic. For the regularized solution SSE=23148788.888227Hz², prior quadratic100.370378 and augmented loss1581.892866. These are not localization NLLs. Original common coefficients remain unpenalized, as in the prior representability audit; no prior strength was tuned from outputs.

Scaled data conditions are1761.425544(common),1770.158800(fractional),3479.432401(combined). The regularized augmented design condition is1766.699816. All data designs have full column rank; complete data/augmented singular arrays, coefficient names/scales/boxes and residual summaries by RX×band/time are retained. Regularized RX0 low/high RMS64.615494/115.263560Hz; RX1 low/high81.191420/153.595830Hz. The remaining early-bin0 RMS212.295060Hz and late-bin14 RMS155.782669Hz show the residual is not eliminated.

The source functions were fitted with different geography, orbital timing and q; calibration can absorb those differences. Therefore the contrast gain cannot identify hardware behavior, validate RF mapping, establish independent band noise, or show improved position accuracy. No projected coefficient is used as a localization seed. A new scientific model control would need its own nested objective/gradient/normalization qualification and explicit bounded protocol; the present evidence does not displace the rejected-profile numerical-finishing investigation.

Output: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-b-clock-compatibility-059-v1`, internal120/TERM135/KILL140. Terminal SHA256 `2bc1b1dca800c2ceaa4044d0bfa1253ff6c46828c99233fad19c999be87ff6e3`; seal `79c725de2169a7b8fd479fc57d86296371f5cf408f8b1d7925078d762cf4fe46`.
