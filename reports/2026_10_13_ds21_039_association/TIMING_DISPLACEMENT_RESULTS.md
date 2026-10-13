# DS21-039 finite timing-compensation displacement

The original all-band state's local quadratic prediction remains useful over the tested 1 km compensated rays. The refined state's negative ray is substantially more expensive than its local quadratic prediction. All eight exact MAP objective changes are positive. This tests finite behavior of the saved linear compensation directions; it establishes neither a position-accuracy improvement nor a finite nuisance-profile minimum.

The protocol evaluates exactly the original all-band and old seven-call refined all-band fitted-c states, both saved finite-difference steps, and both displacement signs. Each point moves geography by 1 km along its saved weak axis and moves calibration/timing by the corresponding saved linear compensation. The east-positive axes are approximately `(0.770, 0.638)` and `(0.810, 0.586)`. All eight original constraints and native bank supports were preflighted before evaluation. Observations, native candidates, objective, learned common-c layout and physical priors remain original; no optimizer, extra baseline, reference or held call was made.

`h` identifies the source curvature step, not the 1 km displacement amplitude. Taylor predictions include the exact saved baseline gradient, with likelihood and prior terms separated. Positive changes mean worse training fit/objective relative to the respective saved endpoint.

| Endpoint | h | Sign | Exact ΔMAP | Taylor ΔMAP | Exact − Taylor | Exact ΔNLL | Exact Δprior |
|---|---:|:---:|---:|---:|---:|---:|---:|
| Original all | 1e-4 | − | 4.699 | 4.536 | +0.164 | 5.491 | −0.791 |
| Original all | 1e-4 | + | 4.330 | 4.536 | −0.206 | 3.505 | +0.825 |
| Original all | 5e-5 | − | 4.699 | 4.536 | +0.163 | 5.491 | −0.791 |
| Original all | 5e-5 | + | 4.330 | 4.536 | −0.207 | 3.505 | +0.825 |
| Refined all | 1e-4 | − | 7.302 | 3.358 | +3.944 | 7.670 | −0.369 |
| Refined all | 1e-4 | + | 3.429 | 3.358 | +0.071 | 3.018 | +0.411 |
| Refined all | 5e-5 | − | 7.307 | 3.270 | +4.037 | 7.678 | −0.371 |
| Refined all | 5e-5 | + | 3.430 | 3.270 | +0.160 | 3.015 | +0.415 |

The original Taylor error is approximately 4–5% of the predicted increase. The refined negative-ray error exceeds the predicted increase itself. Exact values are nearly unchanged between the two saved directions: the largest step-to-step objective difference is 0.0052, despite the previously reported 2.6% variation in the refined weak local eigenvalue. The original prior is exactly quadratic along these rays: maximum prior Taylor error is `5.2e-14`, and maximum objective/NLL/prior ledger error is `4.3e-12`. The substantial refined mismatch therefore arises in the marginal likelihood along the finite ray, rather than in prior arithmetic.

The posterior comparison is **plus versus minus**, whose spatial points are 2 km apart. It is not a comparison with the original state. All summaries retain 2,798 original windows.

| Endpoint | h | Mean posterior TV | Maximum posterior TV | Changed maximum-posterior labels |
|---|---:|---:|---:|---:|
| Original all | 1e-4 | 0.012603 | 0.590710 | 47 |
| Original all | 5e-5 | 0.012603 | 0.590709 | 47 |
| Refined all | 1e-4 | 0.009794 | 0.926088 | 39 |
| Refined all | 5e-5 | 0.009804 | 0.926524 | 39 |

These labels are model satellite/clutter allocations, not independently measured emitter identities. The summaries show concentrated posterior changes, but they do not identify which observations cause the refined Taylor failure or establish a clock/TLE fault. Quarter-second bank interpolation and discrete visibility remain limitations of a smooth local curvature interpretation. This check does not optimize the nuisances at the displaced positions, so it cannot determine the actual finite profile minimum or compare localization accuracy.

Independent receipt audit verified all 338 live/archive source pairs, nine immediate ancestor bindings, original input/bank/attempt/seed bindings, inherited cold/refinement/curvature source subsets, the successful curvature 10-file seal, all eight launches/results/terminations/endpoint seals, four pair receipts and the displacement 38-file aggregate seal. Each point's saved source, prescribed curvature step, 1 km displacement and physical bounds match. The sealed result reports eight objective/gradient calls, zero optimizer calls and no held/reference use; diagnostic runner time is 0.444 s. Frozen limits are 90 s internally, TERM 105 s and KILL 110 s, including the recipe's training preparation. Bindings and compact numerical results are in [TIMING_DISPLACEMENT_AUDIT.json](TIMING_DISPLACEMENT_AUDIT.json); immutable full point receipts remain under `local/timing-displacement-v1/diagnostic` in the root-cause report directory.

The next supported experiment is four bounded nuisance-only fits with geography fixed at the first saved step's ±1 km positions for both endpoints. Initialize each from its already evaluated compensated vector and retain fitted c, the original candidates/priors, and equal 20 s/600 budgets; retain failed/nonstationary results. This separates an inadequate finite linear compensation ray from asymmetry of a locally optimized nuisance profile. Four single-start fits cannot establish global minima. It introduces no new prior setting or reference-based constraint choice. The [fixed-geography timing protocol](FIXED_GEOGRAPHY_TIMING_PROFILE_PROTOCOL.md) records the prescribed experiment, which has not been run in this audit.
