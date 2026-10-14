# B059 nuisance coupling improves a nearby mode, but the far mode still wins

The authorized common-incumbent-nuisance control completed **all6 v2 fits in28.650s**, within the original20-second/600-iteration caps and whole180/195/200 bounds. All three fixed profiles and all three free releases passed independent objective/NLL replay, physical/nuisance feasibility and the unchanged KKT≤.001 criterion. All scientific outcomes were sealed before reference evaluation. Final training selection retains the far mode: **333.217856km**, with no promoted improvement.

The donor-position profile does provide causal evidence of coupled initialization: at **exactly the same geography**, copying the incumbent's complete non-geographic state and refitting reduces objective by183.817344 versus the previously fitted A-derived B endpoint. That includes127.344980 lower NLL and56.472364 lower prior penalty. It does not isolate clock, c, group calibration or satellite timing individually. The subsequent accepted free release is1.077617km from the development reference, but its objective remains117.247680 worse than the incumbent. Choosing it by error would be an oracle result and is prohibited.

## Matched starts, original disks, actual outcomes

All profiles change only XY from the same selected incumbent vector/nuisance. Their positions come from three already sealed training states: incumbent B continuation, fitted A-derived B donor and original B full/start3. The source and current modes have the same full B observations, bank, timing basis, calibration frame, folded Gaussian/common-clock/group objective, priors and fitted c. No reference supplied a start or domain.

The incumbent retains its original proposal1 center `[125,175]`; both nearby positions retain original proposal3 center `[-97.65564087158711,-96.14540367890797]`. Every radius remains25km. All six actual raw starts are feasible and show **zero source-initializer adjustment**; no projection or clipping was performed. All three profiles ran before any release. Each release received its profile's exact returned physical/nuisance state and its same original disk.

| Training position | Stage | Objective | NLL | Prior penalty | Independent KKT | Actual evaluations |
|---|---|---:|---:|---:|---:|---:|
| Incumbent | Fixed profile | 33803.698786 | 33200.283991 | 603.414795 | .000284863 | 12 |
| A-derived B donor | Fixed profile | 33943.998819 | 33526.345718 | 417.653100 | .000507797 | 485 |
| Original B/start3 | Fixed profile | 35759.995436 | 35338.789608 | 421.205829 | .000295941 | 507 |
| Incumbent | Free release | 33803.698786 | 33200.283991 | 603.414795 | .000230170 | 18 |
| A-derived B donor | Free release | 33920.946467 | 33511.231597 | 409.714870 | .000045558 | 277 |
| Original B/start3 | Free release | 35735.930388 | 35312.223779 | 423.706609 | .000093628 | 325 |

The incumbent control reproduces its original objective/position within floating arithmetic. At the donor point, the fixed profile still loses140.300032 versus that control. Its free release reduces that deficit to117.247680: likelihood is310.947606 worse, partially offset by193.699925 less prior penalty. Thus the residual ranking is not a prior-only rejection of this closer accepted endpoint.

At the original/start3 geography, the shared-incumbent nuisance initialization instead converges to a worse fixed-position basin: objective+1395.925267 and NLL+1462.741054 versus the already saved original/start3 state. The profile is stationary, not globally optimal. Retaining all six original endpoint eligibility flags is essential: a common initialization is not universally better, and these controls do not establish that nuisance profiling exhausts every mode.

| Free release | Objective gap to incumbent | Development-reference distance, km | Training selected |
|---|---:|---:|---|
| Incumbent | 0 | 333.217856 | yes |
| A-derived B donor | +117.247680 | 1.077617 | no |
| Original B/start3 | +1932.231602 | 14.405426 | no |

The selector compares accepted releases with all six original accepted full B endpoints using training objective, then declared ordinal. The new incumbent continuation wins only by floating-scale objective difference and is physically equivalent to the original selected mode. Nearby error values are retrospective diagnostics, not new seeds, selector inputs or changes to the baseline histogram.

## Preserved v1 failure and v2 qualification

V1 (`b6d7a86b5`) made one incidental optimizer call in13.199s and preserved its raw returned endpoint. The reused original039/023 audit conflated fixed geographic XY with the disk center: incumbent XY `[125.4780514599,175.6649793143]` differs from the preserved original center `[125,175]`. The fit correctly held its prescribed point, but that helper raised `Profile changed fixed geography`. V1 has no scientific terminal, no release and no reference join. It is an adapter audit failure, not a failed scientific fit or accuracy result, and remains immutable at bulk `model-b-common-nuisance-profile-059-v1`.

V2 (`e0b34c72e`) explicitly separates fixed XY from original disk center/radius, binds the v1 failure receipts/source authority before preparation and preserves all scientific options. Its actual-fit regression holds XY `[3,4]` in a disk centered `[2,2]`; it also rejects wrong fixed XY, NLL replay mismatch, residual KKT and invalid nuisance bounds. A feasible timing-face endpoint records the source's tiny initializer margin without being treated as infeasible. Combined v1/v2 tests:13 passed in2.44s, Ruff passed. No original fitter, scientific model, physical constraint or acceptance threshold changed.

Count **1 incidental v1 call plus6 new v2 calls**, in addition to original18 B view fits,18 A path fits and the prior059 donor/control pair. These are explicitly extra experimental calls, not an equal-cost end-to-end search comparison. No retry or further polishing follows this result.

## Supported conclusion

Calibration/timing coupling explains part of the previous donor state's disadvantage; fixed-state receiver/channel contrasts were therefore insufficient to prove an unavoidable geographic likelihood bias. The matched profile nevertheless leaves a stationary,1.078km candidate behind the333.218km mode by117.248 objective units, predominantly likelihood. This narrows the remaining question to further nuisance/association modes or observation-model preference; it proves neither that global search is exhausted nor that a particular new parameter repairs localization. The native fixed-state audit and passing-branch bounds remain relevant but were performed at earlier physical states. No blanket prior relaxation, temporal reweighting or endpoint promotion is justified here.

Runtime `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-b-common-nuisance-profile-059-v2`. Scientific terminal SHA256`28305c700471e99a74ef002b784bfee50d2c6a6191422115ecc553ae2d755b19`; seal`c0ae955a59011aa2ea8d5b5f81f6c91a69dfe1d4bd42b2769cfb8370877bbf9a`; postseal evaluation`b721a89beeaba7adce1a52869b5dc1354e844078a948271e17b4465d55055a81`. All raw seeds, original disks, source initializer receipts, returns, fixed/free audits, original eligibility and exact training selection remain reviewable. Original baseline selections and histogram rows are unchanged; the sub-kilometre full-band target remains unmet.
