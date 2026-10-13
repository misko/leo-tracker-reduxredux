# DS21-039 fixed likelihood-scale sensitivity

The predeclared alpha=0.25 sensitivity improves this development position error by **142.035 m**, from **4.072515 km to 3.930480 km**. Both conditions remain far above the user's 0.5 km target; the quarter-scale result also remains worse than the earlier separately fitted low/high views. This is a modest sensitivity result, not a solved root cause or a release candidate. Alpha was fixed before this comparison and is not selected by these errors.

The control compares `alpha * original marginalized observation NLL + original priors`, with alpha=1 and 0.25. Both use the same original all-view and sealed refinement physical starts, original seed-5 25 km disk, 2,798 windows, 3,714 retained native alternatives, 43 satellites, fitted common c, calibration frames and parameter bounds. Common/relative timing and group priors remain applied once, unchanged. There are zero temporal edges and no measured waveform identity evidence. No held observations or reference position entered fitting or training selection.

| Selected condition | Own composite objective | Scaled observation NLL | Original untempered NLL | Unscaled prior cost | Actual native RMS, Hz | Post-seal error, km |
|---|---:|---:|---:|---:|---:|---:|
| Alpha=1 | 32,380.954535 | 32,225.181022 | 32,225.181022 | 155.773513 | 92.162359 | 4.072514870 |
| Alpha=0.25 | 8,211.590993 | 8,056.924690 | 32,227.698761 | 154.666303 | 92.173513 | 3.930480309 |

Both select the actual new fit from the refinement start. The unchanged alpha=1 selector also includes the two original stationary source incumbents, retaining a stronger baseline; its declared objective/name tie rule chooses the new refinement continuation. Alpha=0.25 does not automatically promote either old source state. Scores across alpha are different composite objectives and cannot be ranked as one common likelihood.

Untempered NLL **worsens by 2.517738**, native RMS worsens by **0.011154 Hz**, and prior cost decreases by **1.107209**. Selected signal/clutter mass changes from 2,167.247596 / 630.752404 to 2,166.921034 / 631.078966. Thus the modest post-seal position improvement does not come with better original frequency fit. Common c changes −618.997814 → −622.332150 Hz/GHz; these fitted values are not measured hardware calibration.

| New attempt | Composite objective | Untempered NLL | Prior cost | Stationarity | Fit seconds / evaluations |
|---|---:|---:|---:|---:|---:|
| Alpha=1, original-all | 33,172.423429 | 32,969.499770 | 202.923659 | 5.357e-4 | 0.573 / 21 |
| Alpha=1, refinement | 32,380.954535 | 32,225.181022 | 155.773513 | 7.042e-5 | 0.769 / 29 |
| Alpha=0.25, original-all | 8,440.582016 | 32,968.611471 | 198.429148 | 6.931e-5 | 5.926 / 228 |
| Alpha=0.25, refinement | 8,211.590993 | 32,227.698761 | 154.666303 | 1.720e-5 | 5.558 / 210 |

All **four fits are stationary, solver-successful and interior**, with no 20-second ceiling hits or retries. Summed new fit time is **12.827 s / 488 evaluations**, runner time **13.176 s**, and root's reported outer preparation-plus-fit time **39.051 s**. These are different timing scopes. Exact parameter arithmetic verifies the original bounds and physical constraint minima: maximum absolute total satellite shift is 16.210 s within ±20 s, and maximum distance from the shared seed-5 center is 9.369 km within 25 km.

The selected prior ledger is common timing **0.130191 → 0.140927**, relative timing **155.243574 → 154.125640**, and group calibration **0.399748 → 0.399736**. It shows only a modest reduction in relative timing penalty; large total shifts remain. This does not establish physical ephemeris/UTC errors or resolve association/calibration confounding. After overall objective rescaling, alpha=0.25 is equivalent to quadrupling all Gaussian prior precisions together, not a measured covariance or independent sample count.

Independent receipt-only verification passed all **329 live/archive source pairs**, six ancestor bindings, four launch/termination/attempt identities, original two source states, exact timing-basis/domain checks, composite/source score labels and minimum stationary selectors. The alpha=1 actual source oracle closes both original parents exactly in saved objective/NLL, both gradients, satellite/clutter probabilities, residuals and prediction gradients. All four prior ledgers reproduce within **1.68e-12**. Selected diagnostic costs replay exactly.

Native RMS retains actual branch second moments through the existing native audit, including an explicit NLL/posterior closure gate. It differs from the historical fitter's collapsed conditional-mean residual RMS: the selected alpha=1 values are 92.162359 versus 92.149562 Hz, and alpha=0.25 values are 92.173513 versus 92.161356 Hz. The symmetric ±100 Hz regression produces zero conditional mean but 100 Hz native RMS. Do not interpret the collapsed metric as native spread.

The initial [v1 interface failure](LIKELIHOOD_TEMPERING_FAILURE_V1.md) remains preserved: one launch/termination, zero optimizer callbacks, no attempt/terminal/selection. Its wrapper accidentally shadowed the geographic prior object; root authorized the narrow ledger-method rename and a fresh v2 namespace. Statistical arithmetic, alpha choices and physical states were unchanged. **24 component tests**, including actual tiny fitter/SLSQP callbacks for both alphas, passed before v2 freeze; Ruff and source review passed. Current v2 source bytes are not claimed to match the failed v1's preserved archive.

Primary v2 seals: freeze `ee164c2cd95554a8f38f738d45c6219b5c2b792c2d3b2f8169110c41764abbdc`; training terminal `aaa1a376404d02b4c92d513b93974dff96b89e22627fb1db381c836e874c305e`; source oracle `1068a28ff810d268ef3a64280e1e917a4b15f7e2ddc6cfd7af24d3a1721ee4c6`. Exact bindings, all four outcomes and the root post-seal evaluation binding are in [LIKELIHOOD_TEMPERING_RESULTS.json](LIKELIHOOD_TEMPERING_RESULTS.json). This audit invoked no predictor, likelihood, optimizer, held scorer or reference function. Root's configured station reference is not an independently surveyed location in this work.

Retain this outcome without promotion or an alpha sweep. Any next step must be a prespecified transfer comparison on fixed development records, preserve failures and separate likelihood/prior effects from position accuracy; this one case cannot establish full DS21 performance.
