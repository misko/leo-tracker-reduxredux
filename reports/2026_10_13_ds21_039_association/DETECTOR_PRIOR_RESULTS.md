# Detector-winner prior control: negative localization result

The fixed δ=0.25 native-alternative prior is **not promoted**. All four prescribed fitted-c fits were stationary, but its training-selected position worsened from **4.072515 km to 4.409778 km**. The changed condition remains far above the user's 0.5 km target. δ is the native-candidate prior fraction, not the RF coefficient c.

Both conditions used the same original all-band winner and sealed seven-call refinement winner as physical starts, the unchanged 43-satellite bank, original seed-5 center/25 km disk, and 20-second/600-iteration budgets. The expanded inventory retains 7,622 native candidates from 2,798 original windows, including 3,908 formerly discarded alternatives. δ=0 assigns mass only to the original cell winners; δ=0.25 reserves 75% of each nonsingleton cell's mass for its detector winner and divides the other 25% among alternatives. Cell mass, clutter and satellite priors remain fixed; visibility masks without renormalization. Waveform evidence is neutral and temporal edges remain zero.

| Training-selected condition | Objective | Native likelihood NLL | Physical prior penalty | Native posterior RMS, Hz | Signal mass | Alternative fraction of signal | Post-seal error, km |
|---|---:|---:|---:|---:|---:|---:|---:|
| δ=0 | 32,380.955 | 32,225.181 | 155.774 | 92.162 | 2,167.248 | 0% | 4.072515 |
| δ=0.25 | 32,197.315 | 32,041.514 | 155.802 | 91.431 | 2,227.624 | 19.6235% | 4.409778 |

Both selected new fits started from `refinement-free`. δ=0 reproduces the sealed original-prior refinement result. Under δ=0.25, NLL falls by 183.667, native RMS falls by 0.731 Hz, signal mass increases by 60.376 and discarded alternatives receive 437.139 units of posterior mass. The physical prior penalty changes by only +0.0281. Nevertheless, position error increases by **0.337263 km**. The two likelihoods use different native-candidate priors; their frequency-score difference is not independent validation or evidence of correct identities. Native RMS also differs from the legacy RMS of branch-averaged residuals: the latter is 88.525 Hz for the selected δ=0.25 fit and can conceal disagreement between alternatives.

| Condition / physical start | Fit seconds | Evaluations | Stationarity | Solver success |
|---|---:|---:|---:|---|
| δ=0 / original-all | 0.988 | 21 | 5.36×10⁻⁴ | true |
| δ=0 / refinement-free | 1.219 | 25 | 7.04×10⁻⁵ | true |
| δ=0.25 / original-all | 11.385 | 228 | 3.61×10⁻⁶ | true |
| δ=0.25 / refinement-free | 11.399 | 235 | 2.73×10⁻⁴ | true |

Exactly **four** calls completed, with four stationary outcomes and four solver successes, 509 reported evaluations and 24.991 aggregate fit seconds. No path reached its 20-second limit and no failures were retried. Runner elapsed time was 29.420 seconds; the coordinator reports 54.628 seconds including preparation. These times include different optimizer trajectories and are not an isolated evaluator benchmark. The 80-second fit allocation and 180-second external ceiling were respected.

Before fitting, δ=0 replayed objective and NLL exactly at both frozen source states. Maximum vector/nuisance gradient differences were 2.05×10⁻¹³ / 1.37×10⁻¹⁶; satellite/clutter posterior differences were at most 3.89×10⁻¹⁶. Both selected outcomes replayed their own objective and NLL exactly. An independent receipt-only audit verified all **326 live/archive source pairs**, six ancestor bindings, twelve attempt/launch/termination files, two-start oracle coverage, four-call accounting and minimum stationary training selection, with no discrepancies. Nineteen component synthetic tests and Ruff passed before freeze.

The coordinator joined configured-reference errors only after sealing; that station reference is not independently surveyed here. No reference or held observations entered fitting or selection, and no held score was computed by this control. This report author checked sealed receipts, hashes and receipt arithmetic only; no model replay, orbit evaluation, optimizer or raw-reference read was performed.

This result rejects promotion of this particular winner-preserving alternative prior. It does not prove that the original detector winners are true, that discarded alternatives are noise, or that the satellite bank is complete. Earlier equal-alternative preservation had mixed results on DS21-005/023, and assumed receiver coupling and the subsequent DS21-039 observation-weight controls also failed their localization comparisons. Together these outcomes show that improved frequency fit, candidate support and stationarity have not resolved the remaining association/physical-model ambiguity. Do not sweep δ or expand the case grid from this result. The next step is a source/metadata audit for actual recorded antenna direction or response evidence; a directional prior requires attested provenance rather than an invented angular cutoff.

Source binding: `reports/2026_10_13_ds21_039_root_cause/local/candidate-prior-v1/freeze.json`, SHA256 `215b282356066d59d9362286c04cdf84883c113aeb23e82ae4ed4eb0cd804aae`; fitted terminal SHA256 `3dea77c54735573ded8f07368aab9aa760759e2ef0c43c4cff6b60265f4ceaf2`; source-oracle SHA256 `2597d6c1b4e0d3e5e74e34901a4ffc5905d90e848a2e67121ee7857b418181a3`. The coordinator's `development-errors.json` binds the same terminal, freeze and immutable membership. All attempt and source archives remain preserved in the coordinator's local output.
