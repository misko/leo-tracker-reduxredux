# Past paid detections recover 49% of omitted dense owners at the larger budget

Buying an omitted lane after a recent same-radio positive recovered **707 of 1,452** dense original-owner lanes in both calibration arms. Equal-cost, evenly spaced recovery found **530**, and a uniform draw within the same streams was expected to find **534.3**. The causal rule left an estimated **2.992 CPU s** in receiver savings, but fell **19 owner lanes short** of the frozen half-coverage gate. No saved position fit followed. The budget that preserved the 4.616 s gate recovered just **27 owners**. [Frozen protocol](causal-mask-recovery-protocol.md) · [Scored receipt](measurements/causal-mask-recovery-score.json) · [Sealed purchase plans](measurements/causal-mask-recovery-plans.json.gz)

## Matched causal and uniform recovery

Both rules started with the original target mask. They paid for every genuine base search, including full stereo anchors. At each omitted short lane they saw only the earlier base-paid results on that same receiver, exact RF, channel and pilot edge. The recent-positive rule asks whether the last paid search was positive within eight hardware-counter seconds. The signed-slope rule requires two consecutive positive paid searches within the same horizon and no more than 8 kHz/s of change. Both thresholds come from the released continuation rule. Empty paid searches matter to both policies. Bought-back observations were billed once and excluded from prediction history. The entire schedule was sealed before opening the omitted detector outputs or original owners for scoring. There is no dependence on orbit or location, the current peer, known owners or the omitted lane's measurement.

Each lane allocated its running quota based on omitted opportunities seen so far. Unused shares carried forward. At the end of each replay the comparison placed the same number of purchases at midpoint positions of equal-sized bins in that stream. An additional baseline averaged over a uniform draw using the same realized per-stream counts. This controls aperture, number of billed calls and exact RF/radio allocation. The comparison uses the full stream extent to set its retrospective even spacing.

| Dense rule and quota | Bought short lanes | Empty | Other positive | Original owners recovered, either arm | Matched uniform, actual / expected | Estimated receiver savings after policy CPU, s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Recent positive, 1/64 | 64 | 17 | 20 | 27 | 22 / 21.0 | 4.659 |
| Recent positive, 1/8 | 542 | 186 | 130 | 226 | 184 / 177.8 | 4.148 |
| Recent positive, 1/4 | 1,094 | 347 | 282 | 465 | 384 / 359.0 | 3.559 |
| Recent positive, 3/8 | 1,625 | 513 | 405 | 707 | 530 / 534.3 | 2.992 |
| Signed slope, 1/64 | 64 | 30 | 13 | 21 | 22 / 21.0 | 4.659 |
| Signed slope, 1/8 | 536 | 257 | 109 | 170 | 176 / 176.0 | 4.154 |
| Signed slope, 1/4 | 948 | 420 | 213 | 315 | 315 / 312.9 | 3.714 |
| Signed slope, 3/8 | 1,070 | 444 | 273 | 353 | 353 / 358.7 | 3.584 |

The dense target mask omitted 4,435 genuine search opportunities, including 2,414 positives and 1,452 original owners. A bought positive outside the original owner set could still support a new inference. This test counts it separately and makes no position claim about either type of bought factor. The highest-coverage recent-positive policy left 745 original owners unmeasured. It gained 11.9 percentage points on the higher uniform baseline. The earlier 1,452-lane hindsight restoration achieved 0.704 / 0.661 km with 3.185 s estimated native savings, but original owners are unavailable before a location fit. This replay covers a smaller subset, buys 918 lanes outside that oracle set and leaves its own positions unmeasured. [Base mask and shared-fit failure](stereo-mask.md)

## Transfer and accounting

| Offer, 3/8 quota | Recent positive owners / possible, uniform | Signed slope owners / possible, uniform | Recent / slope buys | Recent / slope estimated receiver savings, s |
| --- | ---: | ---: | ---: | ---: |
| Weak DS30-0016 | 15 / 37, 15 | 5 / 37, 6 | 112 / 72 | 0.363 / 0.404 |
| South containing | 118 / 154, 39 | 115 / 154, 32 | 187 / 140 | 0.594 / 0.641 |

The recent-positive advantage transferred to South. It matched the weak deterministic uniform count at this quota. Signed smoothness strongly selected Southern owners but gave no dense improvement and reduced weak recovery relative to uniform. At 1/64, no weak or South stream accumulated enough budget to buy a lane. All other tested dense quotas retained more than the 2.735 s first-sixteen target. Only the 1/64 quota retained the 4.616 s first-four target. All savings use the original complete acquisition's aperture-specific mean CPU, with dense short calls priced at 1.068 ms. They also charge the measured Python pass through the resident saved packet, **7.7–9.1 ms dense** including mask-counter replay. All original full calls, decode, hash and nonnative ingress remain charged. These are receiver-work projections before any solver change, waveform timing variation, publication or process exit. [Measured original receiver clocks](measurements/dense-full-short-raw.json.gz) · [Roster projections](roster-savings.md)

The 3/8 recent-positive rule passed the uniform and transfer comparisons and missed the half-coverage condition. No rule qualified for a new dense fit. The two fixed rules leave open a policy using purchased outcomes to update its causal evidence while charging them. That feedback, genuine I/Q timing, new location tests and omitted-region decisions were outside this experiment.

The protocol, rules and tests were frozen at `633bdf6eb`. Nine focused and adjacent tests passed. Run `causal_mask_recovery.py plan NEW_TMPFS_DIR` on the three saved target detector packets before `causal_mask_recovery.py score NEW_TMPFS_DIR`. Use the shared Gauss lock, CPU 2, nice 15, I/O priority 7 and one numerical thread. The plan receipt expands to SHA-256 `fd16998ac56979d9efffbf3805d4ebe74934c6d37477d9d099078a03600fa1f3`. The scored receipt hashes to `74c23da94c06b07b5b66d3c6d6688c97eade7adf3c20eef58efdd723b1352a39`. No waveform inputs were opened. [Causal policy and scorer](causal_mask_recovery.py) · [Component tests](../../../tests/pipeline_eval/test_causal_mask_recovery.py)
