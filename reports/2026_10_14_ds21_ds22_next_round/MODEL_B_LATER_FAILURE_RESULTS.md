# Current B053/B059 failures: coupled modes, not one common root cause

The new source-frozen audit completed in **19.599 seconds with 18 objective evaluations and zero fits**. Its internal/external bounds were 120/135/140 seconds including preparation, one worker, fitted c only. All own objective/NLL and band-sum replays closed within 1e-7. Inputs are the sealed current coverage cached-v2 parents, not historical originals or mixed-version best halves. No reference or held data entered the audit. Existing development-error receipts are used below only for retrospective interpretation.

| Current after case | A all km | B all km | B low km | B high km | C all km |
|---|---:|---:|---:|---:|---:|
| 053 | 226.014213 | 242.261759 | 59.406856 | 242.215064 | 253.925456 |
| 059 | 3.673872 | 333.217856 | 6.741339 | 2.563161 | unavailable |

**059 is a fusion/basin failure with nearby training-derived alternatives already present.** All 18 B endpoints are stationary and all six full endpoints are interior. Full start3 loses the selected distant start1 by objective560.371383 and NLL675.764562 despite a **115.393179 lower prior**. The difference is low-band NLL+862.166870 and high-band NLL−186.402308. The current near full solution is therefore not rejected solely by a prior, time cap, disk boundary, or absence of a nearby initial proposal. A's training-selected full path and both B halves independently locate nearby regions. This is evidence of a coupled optimization/likelihood mode problem, not proof of a unique correct association or an accuracy fix.

**053 has a broader current-bank/start failure.** B full accepts four of six endpoints. Rejected starts1/3 have worse raw objectives than the accepted winner; they do not hide a lower-score full solution. The winner beats every other full endpoint, including rejected ones, on **both** band NLLs. Its low band remains791.957191 worse than the independently fitted low-half winner; its high band is only30.144163 worse than the high-half winner. A and C also select distant solutions. The separate A053 inventory records42→51 candidates,34 shared,8 removed,17 added, and only two old centers retained. Unlike035, the old B-all and B-low endpoints remain inside current disks (minimum23.495/4.064km). Before B-all36.080444→after242.261759km is a version-paired regression, not evidence that the unchanged old endpoint would win under the new bank. Bank/initialization changes remain a separate hypothesis; current after-only scores cannot isolate them.

The original six centers and full outcomes are retained below. Every original fit used its own unchanged25km disk,20-second/600-iteration budget. XY coordinates are local training frame coordinates, not reference locations.

| Case/start | Proposal | Center XY km | Stationary | KKT | Radius km | Objective | NLL |
|---|---|---|---|---:|---:|---:|---:|
| 053/0 | cold-0 | −137.5,−112.5 | yes | .000114 | 13.718 | 27149.668344 | 26609.871308 |
| 053/1 | cold-1 | 125,175 | no | .581234 | 5.231 | 25857.990966 | 25087.458099 |
| 053/2 | cold-2 | 125,25 | yes | .000144 | 8.548 | 25966.687075 | 25481.023158 |
| 053/3 | shape-low | 107.519,39.583 | no | 2.558515 | 11.469 | 25280.690684 | 24737.701248 |
| 053/4 | shape-high | −52.729,−143.454 | yes | .000087 | 25.000 | 27352.173388 | 26905.583164 |
| 053/5 | shape-all | 125.416,50.647 | yes, selected | .000369 | 11.357 | 25147.777833 | 24603.323945 |
| 059/0 | cold-0 | −125,−75 | yes | .000354 | 5.950 | 34876.642375 | 34320.340703 |
| 059/1 | cold-1 | 125,175 | yes, selected | .000352 | .819 | 33803.698786 | 33200.283991 |
| 059/2 | cold-2 | −81.25,−231.25 | yes | .000422 | 15.562 | 34991.377992 | 34189.404176 |
| 059/3 | shape-low | −97.656,−96.145 | yes | .000567 | 5.483 | 34364.070170 | 33876.048553 |
| 059/4 | shape-high | −89.314,−123.566 | yes | .000139 | 21.326 | 35954.237812 | 35586.712639 |
| 059/5 | shape-all | −81.162,−81.839 | yes | .000358 | 6.524 | 35442.384828 | 34907.625086 |

053 low accepts6/6 (start0 selected), high5/6 (start2 selected; rejected start1 KKT.144675). 059 low/high each accept6/6 (starts3/5 selected). A solver success flag does not override independent stationarity: all three rejected053 B calls returned solver success. There were no new endpoint-polishing calls.

Frozen-function swaps show coupled calibration and orbital timing rather than a single faulty scalar coefficient:

| Case/band | Windows | Full orbit+calibration NLL | Full orbit+half calibration | Half orbit+full calibration | Half orbit+calibration |
|---|---:|---:|---:|---:|---:|
| 053 low | 1274 | 16833.167618 | 17487.888272 | 17179.459840 | 16041.210426 |
| 053 high | 596 | 7770.156327 | 8460.310983 | 8734.012363 | 7740.012165 |
| 059 low | 1550 | 20526.703401 | 22380.493655 | 21805.813995 | 19061.759920 |
| 059 high | 972 | 12673.580590 | 14183.981754 | 14204.180520 | 12042.598151 |

Every calibration-only or orbit/timing-only replacement worsens the relevant band. The paired half replacement recovers each half score. The orbital block includes geography **and** common/relative satellite timing; this is not a geography-only causal test. Frozen full/half correction functions are evaluated at the same physical timestamps/RFs in their original frames. Hybrids need not be feasible calibrated states and their scores are not calibrated-model evidence. Linear/clock/group component differences depend on gauge; total correction differences are physical.

| Case/band | Full clutter mass | Half clutter mass | Assignment mean TV | MAP switch fraction | Satellite switches among both-signal rows |
|---|---:|---:|---:|---:|---:|
| 053 low | 657.644 | 446.578 | .696304 | .718210 | 581/581 |
| 053 high | 261.894 | 283.820 | .521407 | .535235 | 150/251 |
| 059 low | 778.894 | 449.928 | .781603 | .804516 | 686/687 |
| 059 high | 429.983 | 306.912 | .828569 | .849794 | 416/417 |

These are conditional posteriors at different fitted physical states, including clutter, not satellite identity truth. 059's modes differ strongly in assignments even where both report signal. The full/half relative-timing differences have RMS6.575/5.996s for059 and7.453/5.293s for053. Physical total-correction differences have RMS653.417/2013.013Hz for059 and845.824/13561.621Hz for053 (low/high respectively).

059 full fitted c is−528.764Hz/GHz versus−546.726/−497.870 in low/high;053 full−710.892 versus−663.408/−761.848. Full group offsets are059[−21043.065,37933.163]Hz and053[−27983.609,11913.547]Hz. Their full group prior penalties are only.376347/.185003, while relative-timing penalties are528.180198/475.849367. These are summaries, not an argument to relax or tighten a prior. Half/full coefficient centers differ, so raw coefficients cannot substitute for physical-function comparisons.

## Concrete next experiment proposed, not launched

Test whether an **exact training-selected A-final physical seed** finds an accepted lower-score B mode. Use both cases with identical policy, treating053 as a contrasting failure, and preserve every original B endpoint and its eligibility. For each case, take A's already sealed training-selected stationary final, not a location reference or the endpoint closest to one. Embed its full correction, common clock and satellite timings exactly in the unchanged original B model: preserve its vector/timings and clock nuisance, put the saved A high-minus-low shifts in B's centered group contrasts, and add `high_fraction * shift` to each supported receiver intercept. This algebra preserves the physical total correction (`high*shift`) despite the different contrast gauge. No clipping, calibration relift, new candidate selection, clock model, or prior change is allowed. Source A059 final uses saved shifts[−27520.899662,39226.737197]Hz; its original final objective34240.608125 is still higher than B's distant winner33803.698786, so initialization alone proves no win.

Before any fit, qualify exact bank/observation/frame/clock equality, saved A shift/final authority, full physical-function and orbit closure, B's raw and effective seed domains, and finite objective/gradient closure at the embedded state. Require the same original proposal center and25km disk (A059 start3; A053 start3), with explicit handling of the ordinary initializer margin and no endpoint clipping. If exact equivalence or feasibility fails, stop; do not repair the donor.

Then run exactly **two20-second/600-iteration B calls per case**: the A-final donor and a matched original B-selected-endpoint continuation control, each with its original proposal disk. Four new calls total; no retry; whole pair180/195/200-second caps including preparation and replay. Independently check original B stationarity and objective replay. Training-only selection considers all originally accepted B endpoints plus accepted new endpoints; never replace a better incumbent merely because a new state has smaller position error. Seal both cases and all four outcomes before held/reference joins. Report added optimization budget and A's upstream six three-stage paths separately: this is an extra-budget basin intervention, not an equal-cost replacement of the original six-start baseline. It discriminates a missing calibrated donor mode from a loss model that continues to favor the distant mode; either result may be negative. No fits are authorized or claimed in this report.

## Receipts

Protocol/source commit7cd43bbe6; component/adapter tests8 passed and Ruff passed. V1 freeze remains intact and unlaunched because it omitted the assignment helper from its source closure; v2 explicitly binds it. All1012 source/input/receipt bindings were frozen before preparation and checked again before sealing.

Runtime directory `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-b-later-failure-audit-v2`:

- terminal SHA256 `4d2d6437550951c882c18638d1c3d4a02e5fe3b6cbd4d9e63583ec60df061c0e`
- seal SHA256 `6ea33258d55e2ef3c95d9d08665be00cbe57b4d892d7646e16cd695838047889`
- per-case results retain all six full endpoint band scores, calibration/timing summaries and full/half assignment comparisons.

The sub-km target and full-versus-both-halves target remain unmet. These results establish diagnoses and a reviewable next experiment, not a localization improvement.
