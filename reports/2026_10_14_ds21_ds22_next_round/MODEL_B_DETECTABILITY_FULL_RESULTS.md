# B059 full-training detectability control: density gain does not repair position

Both training selectors still choose the far endpoint. The normalized control remains333.217856km from the configured development reference; learned detectability selects332.957657km. All eight fits pass the unchanged strict acceptance gate. The closer detectability release at1.563192km loses by187.668991 objective units, including409.666440 worse likelihood despite221.997449 lower priors. No model or histogram is promoted.

## Controlled execution

The [protocol](MODEL_B_DETECTABILITY_FULL_PROTOCOL.md) and runner were committed `e530ede67`, with28 relevant component/runner tests passing in2.08s and Ruff passing. This follows the [four-arm conditional development CV](MODEL_B_OBSERVATION_CV_RESULTS.md) and [coefficient audit](MODEL_B_DETECTABILITY_EVIDENCE_RESULTS.md), whose rejected outcomes remain unchanged. The detectability bound, shrinkage, basis and full-bank budget were not tuned after those results.

Source/input authority was frozen before preparation. Actual full-training qualification passed in13.955s with234 objective evaluations and zero optimizer calls: exact source legacy oracle closures at both complete starts, conditional logmass relation, zero-tail normalized nesting, raw domains and every full-training q-tail finite difference. Maximum q-gradient finite-difference errors were7.97350e-8 at incumbent and6.66260e-8 at donor, below the unchanged tolerance.

Four fixed profiles used identical complete incumbent non-geographic state, changing only the two previously sealed training XY coordinates and adding zero q tails. Both profile units were sealed before either release worker launched. Each of the four accepted profiles received exactly one complete-state free release in its own original25km proposal disk. There were eight actual optimizer calls, four per arm; no retries, CV endpoint reuse, polishing, extra starts, clipping or bound/penalty changes. This adds budget beyond all disclosed discovery/initialization, original fits, earlier profiles and sixteen CV calls.

Whole-unit times were17.509s/20.365s for conditional/detectability profiles and15.786s/18.294s for releases. Individual optimizer times were.099–4.853s, within their original20-second/600-iteration caps. Separate stage units used internal120/TERM135/KILL140 bounds including guards, preparation and audits; none waited inside an optimizer slice for the other arm. Two workers ran alongside concurrent DS22/operational processing, so timings are not an isolated speed benchmark. All strict independently replayed KKTs are≤.000854390; every source domain, fixed-XY condition, nuisance bound and objective/NLL replay passed.

## All outcomes, followed by training-only selection

Position errors below were joined only **after the global eight-outcome seal**. No original held or locked measurements were read. Fixed profiles are not eligible free-position solutions.

| Stage | Normalized arm | Training geography | Objective | Conditional-CFO NLL | Development error km | Strict KKT |
|---|---|---|---:|---:|---:|---:|
| fixed |conditional |incumbent |30730.490037 |30127.075242 |333.217856 |.000230165 |
| fixed |conditional |donor |31339.042303 |30900.279933 |1.077617 |.000507604 |
| fixed |detectability |incumbent |29354.758941 |28723.642537 |333.217856 |.000641716 |
| fixed |detectability |donor |29548.083148 |29141.608165 |1.077617 |.000854389 |
| free |conditional |incumbent **selected** |30730.490037 |30127.075242 |333.217856 |.000230124 |
| free |conditional |donor |31218.753777 |30792.183608 |3.480532 |.000135672 |
| free |detectability |incumbent **selected** |29353.994729 |28724.200156 |332.957657 |.000417021 |
| free |detectability |donor |29541.663720 |29133.866596 |1.563192 |.000141713 |

Each selector ranks only accepted free endpoints within its own normalized model by training objective and deterministic ordinal. The original legacy endpoints remain historical controls; neither raw legacy event scores nor target-arm nonstationary states were silently inserted. Known position errors played no role in starts, disks, fitting or selection.

## Likelihood versus priors

The two full-training model arms share a conditional-CFO score convention, but detectability has a separately reported observation prior. Every penalty closes to objective minus NLL.

| Free endpoint | Common timing | Relative orbital timing | Common clock | Group offset | q prior | Total prior |
|---|---:|---:|---:|---:|---:|---:|
| conditional incumbent |.004103 |528.180198 |74.854147 |.376347 |0 |603.414795 |
| conditional donor |.047853 |391.607729 |34.511765 |.402823 |0 |426.570170 |
| detectability incumbent |.004111 |525.717239 |84.732065 |.374161 |18.966997 |629.794573 |
| detectability donor |.011419 |347.536188 |33.915808 |.377854 |25.955855 |407.797124 |

The normalized-control donor loses487.263740 objective units:665.108366 worse NLL minus177.844626 lower priors. Detectability narrows this matched-start ranking gap to187.668991, but its donor still loses NLL409.666440. The remaining full-model ranking is not caused by the donor paying a larger prior or by rejecting an available accepted nearby endpoint.

Detectability improves the far free endpoint's conditional NLL by1402.875086 versus the normalized control, with26.379778 larger total prior, and improves the matched donor release's NLL by1658.317012. These are frequency-model effects; neither establishes a truthful geographic ranking. Earlier nearby original-model endpoints have different coupled nuisance states and local basins; this bounded experiment does not prove a global optimum or exhaustive search.

The whole-bank probability budget remains1.6 with every original candidate retained. Uniform control q is.0280701754 for all57 candidates. Learned far q ranges[.005690,.155510], with two active lower catalogue-basis coefficients; nearby q ranges[.004099,.160690], with three. Sigma stays125Hz in both arms. Active outward lower-face gradients were valid constrained optima in the preceding audit and did not trigger a bound change. Free far/near signal masses are1341.523/1232.326 in detectability versus1313.123/1098.868 in the normalized control; more signal mass is not position truth.

The earlier accepted conditional-CV gain is real within its disclosed development leakage and incomplete nearby comparison, yet it does not transfer to a useful full-training geographic selection on this case. A stable catalogue propensity can support a false geographic mode. This result warrants case-dependent testing of the declared model rather than claiming detectability solved B059, widening its bounds, choosing the near endpoint by truth, or modifying baseline coverage results. Original all-band versus half-band localization targets remain unmet here.

## Frozen receipts

Output: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-b-detectability-full-059-v1`. All source/input and endpoint authority is reachable from its immutable protocol.

| Receipt | SHA256 |
|---|---|
| source/input protocol |`0f080d67c1c241768fae86fbce1a3cb9b2b6cdbda34b521dc07fea00726fc5b4` |
| zero-fit qualification |`8088a0f455dfe1825ae03031ca766eff780f733cd639b310f4869606d842d249` |
| all-eight terminal/selectors |`41e00afbf1e9d8b4577b7260f635ce37079aa0d4910fb7fbd13b3281a314dcc5` |
| pre-reference scientific seal |`eb489cc264648b758df16f4d050dd83e42a2a90c6b42b22285dbc7cb6c864f3a` |
| postseal evaluation |`4bdc85ec9ad7df406f872a87ccbbcb940e65c0f6d32d9923ca1396024b138305` |

Postseal evaluation took12.508s, eight training-objective replays and zero fits. It reports the configured development reference only after both arm selectors were sealed, with original held/locked observations untouched.
