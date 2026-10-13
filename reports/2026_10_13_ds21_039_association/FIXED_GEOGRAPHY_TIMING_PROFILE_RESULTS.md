# DS21-039 fixed-geography nuisance relaxation

All four nuisance-only fits were stationary and improved their exact feasible ray incumbents. The refined state's finite minus/plus asymmetry remains substantial after these local relaxations. This demonstrates additional feasible nuisance adjustment at fixed geography; four single-start fits establish neither global profile minima nor localization accuracy.

The [prespecified protocol](FIXED_GEOGRAPHY_TIMING_PROFILE_PROTOCOL.md) fixes geography at the already evaluated first-step (`1e-4`) ±1 km positions for the original all-band and old seven-call refined all-band states. Initialization uses the corresponding exact compensated vectors. Fitted common c, original native observations/candidates, receiver/group frames, likelihood, timing/group priors, seed-5 disk and physical bounds remain original. Each call has 20 s/600 iterations. The run made exactly four optimizer calls, four prefit replays and four postfit replays, with no retries, reference or held use.

Original endpoint MAP objectives are **33172.423429** and **32380.954535**. Each Taylor prediction includes its saved baseline gradient. All Δ values below are relative to the corresponding original endpoint; ray gain is ray MAP minus fitted MAP. Positive ΔMAP/ΔNLL means a worse training objective/likelihood than that endpoint.

| Endpoint/sign | Taylor ΔMAP | Ray ΔMAP | Fitted MAP | Fitted ΔMAP | Gain from ray | Fitted ΔNLL | Fitted Δprior |
|---|---:|---:|---:|---:|---:|---:|---:|
| Original − | 4.536 | 4.699 | 33176.919879 | 4.496 | 0.203 | 5.328 | −0.832 |
| Original + | 4.536 | 4.330 | 33176.645662 | 4.222 | 0.108 | 3.420 | +0.802 |
| Refined − | 3.358 | 7.302 | 32387.458944 | 6.504 | 0.797 | 6.940 | −0.436 |
| Refined + | 3.358 | 3.429 | 32383.958220 | 3.004 | 0.425 | 2.523 | +0.480 |

Every retained origin is **`new-stationary-fit`**, meaning stationary nuisance optimization with geography fixed. Exact ray states remain preserved as feasible incumbents; they were not claimed stationary. Scaled KKT values are respectively `6.32e-5`, `2.83e-6`, `2.37e-4` and `2.15e-4`, all below the original `0.001` tolerance. No fit reaches a declared boundary. Fit times are 7.06, 6.67, 6.43 and 6.39 s, within the equal budgets.

The complete original prior ledger is retained separately from the likelihood:

| Endpoint/sign | Common timing cost | Relative timing cost | Group cost | Total prior cost |
|---|---:|---:|---:|---:|
| Original − | 0.136617 | 201.555790 | 0.399244 | 202.091651 |
| Original + | 0.103424 | 203.222749 | 0.399456 | 203.725629 |
| Refined − | 0.149386 | 154.788379 | 0.399668 | 155.337433 |
| Refined + | 0.112345 | 155.741754 | 0.399867 | 156.253966 |

For the original state, the minus/plus MAP gap falls from 0.370 on the [linear compensation rays](TIMING_DISPLACEMENT_RESULTS.md) to 0.274 after nuisance fitting. For the refined state it falls from 3.873 to **3.501**, a reduction of about 10%. Thus the saved linear compensation was imperfect, while the refined finite asymmetry largely persists under these initializations. The refined negative fit still costs 6.504 above its source endpoint against the local Taylor prediction of 3.358. A symmetric local Hessian therefore does not describe this finite, locally optimized profile completely.

All four fitted positions remain more expensive than their respective source endpoints. These results do not establish the globally lowest nuisance state, a clock/TLE fault, measured satellite identity, calibrated uncertainty or improved geographical accuracy. No displaced location is evaluated against a reference or selected using position error. The original endpoint accuracy results and full-DS21 acceptance target remain separate.

Independent receipt audit verified all 340 live/archive source pairs, 12 immediate ancestors, inherited cold/refinement/curvature/displacement source subsets and seals, original input/bank bindings, the four launches/results/terminations/attempt seals, run completion and the **21-file final seal**. Every seed equals its sealed step-0 ray state; fitted XY is exactly unchanged. Vector/nuisance layouts, group frames, priors and physical bounds match. Prefit and postfit objective/NLL replay deltas are exactly zero; maximum prior-ledger discrepancy is `5.5e-12`. Signal plus clutter mass closes to 2,798 original windows for each outcome.

The runner reports 27.045 s; the root reports 52.241 s overall including training preparation, within the frozen 150 s internal / 165 s TERM / 170 s KILL limits. [Compact results and binding hashes](FIXED_GEOGRAPHY_TIMING_PROFILE_RESULTS.json) accompany this report. Full immutable receipts remain under `local/fixed-geography-profile-v1/fits` in the root-cause report directory. This independent audit performed no new objective, gradient, fit, held or reference calls and changed no scientific source.
