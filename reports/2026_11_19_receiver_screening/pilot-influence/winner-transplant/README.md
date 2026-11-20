# Geographic effect of capture-era winners missed by both fixed searches

The six prespecified challenge recordings and two preserved controls each have three authenticated, complete native inputs from the same waveform, physical receiver lanes and clock. The controls were selected in the earlier hard-pilots test for examples of winner agreement at sampled visits. Their complete recordings also contain missing measurements. A capture-era winner qualified for an exclusive transplant only when neither the fixed-four nor the fixed-five archive contained a gate-passing candidate within two wrapped epoch samples and 1 kHz of its signed CFO. All four interventions started from the same complete fixed-four native input. [Protocol](PROTOCOL.md) · [Frozen plan](plan.json)

The availability cell includes every qualifying capture-era winner at a stock-negative probe. The conflict cell replaces stock winners at qualifying stock-positive probes, so it preserves the positive-probe roster. The matched availability cell and its placebo add the same number of capture-era winners per physical lane, tuned channel/edge and CFO-sign stratum. Each placebo target already had a physically agreeing gated candidate in fixed five. Pairing prefers nearer recorded visits in each stratum. Median pair separations ranged from 88 to 224 visits across recordings, with longer gaps in the tails. The equal-size contrast can still differ in which track is sampled or at which exact time. [Sealed selections](selections.jsonl.gz) · [Pair support and time separation](matching.csv)

Each transplanted record preserves its original measurements, gate and rank. If that rank already exists, it replaces the stock record in that slot. Competing gates are cleared only when necessary to make the original donor win. The independent audit checks every unchanged packet, surviving competitor, target winner, recording field, bound request and numerical receipt. The positional intervention requires privileged access to the capture-era detector archive. The six challenges have 976 exclusive availability additions and 358 conflict replacements. Their matched contrast uses 631 additions in each cell. The corresponding counts for the two controls are 360, 76 and 234 per matched cell. [Treatment audit](treatment-audit.csv)

The computational scope starts at stored factors and includes both calibration arms for each cell. The installed phase-release receiver ran with one thread on CPUs 8–11, nice 10, a 512 MiB cap, and zero swap. The fixed-four and fixed-five control positions and all four original v5 reference roles come from sealed earlier results. [Resources](resources.csv) · [Capture-era v5 references](capture-era-v5.csv)

## Primary results

Thirty-one of the 32 scheduled fits returned both positions. The DS29-0357 full-availability cell reached the preset last-start horizon before it launched. The primary files and charts retain the unavailable cell. All other challenge fits and all eight control fits completed within the separate 210 s service limit.

The table reports median paired change in error on the six challenge recordings. A negative change means the estimate moved closer to the surveyed position. The count gives closer estimates among the paired numerical positions for each arm.

| Contrast | `c = 0` delta and count | Fitted `c` delta and count |
| --- | ---: | ---: |
| All exclusive availability vs fixed four | −0.235 km, 4/5 | −0.215 km, 4/5 |
| Matched exclusive additions vs equal-size placebo | −0.053 km, 5/6 | −0.012 km, 3/6 |
| Conflicting winner swaps vs fixed four | −0.011 km, 3/6 | −0.011 km, 3/6 |

The full availability cell helped DS29-0082 by 0.400 km in fitted `c`. The matched-size fitted-arm comparison was evenly split, and DS26-0197 favored the placebo by 0.113 km. Across the two controls the matched exclusive additions had 0.089 km higher median fitted-arm error than the placebo. Conflict swaps raised fitted-arm error by 0.870 km on DS26-0122 and 1.221 km on DS29-0082 while keeping their positive-probe counts fixed. Only one of the five completed challenge availability estimates was within 10% of the v5 no-repair error in each arm. The matched additions, placebo and conflicts reached that allowance on zero of six challenges in either arm. [Paired effects](effects.csv) · [Position and v5 allowance scores](scores.csv)

Conditional RF shifted separately. Full availability raised median challenge RMS by 0.701 Hz at `c = 0` and 0.693 Hz with fitted `c` versus fixed four. The matched contrast raised it by 0.207 and 0.201 Hz versus the placebo. Conflict swaps lowered fitted-c RMS by 7.844 Hz on DS26-0122 while worsening its position. The 31 completed services took 36.9–137.3 s after detection, with median wall and CPU times of 86.8 s and 83.7 s. Peak cgroup memory reached 460.5 MiB with zero swap. [Full summary](summary.json) · [Resource receipts](resources.csv)

## Separate make-up

DS29-0357 ran once after the primary batch on its original CPU 9. It used the exact frozen native bits, request, receiver and 210 s service cap. The 166 additional observations raised error from 0.530 to 0.551 km at `c = 0` and from 0.570 to 0.587 km with fitted `c`. Conditional RF RMS rose from 74.262 to 75.369 Hz and from 74.316 to 75.392 Hz. The fit took 87.8 s and peaked at 414.0 MiB without swap. Across the primary and make-up recordings, full availability beat fixed four on four of the six challenges in each arm. [Make-up scores](makeup/scores.csv) · [Separate charts](makeup/charts/README.md)

## Reproduction

Run `python -m tools.pipeline_eval.qualification.winner_transplant_trial /path/to/new/local/work` from a checkout with the original authenticated corpus paths and no existing transplant plan. The work directory keeps the exact derived native and truth-free request files for each cell. Run `python -m tools.pipeline_eval.qualification.winner_transplant_results /path/to/work --plot /path/to/plots` after the position receipt is sealed. [Terminal prediction lock](prediction-lock.json) · [Position charts](charts/README.md) · [Per-recording effects](effects.csv)

The make-up command is `python -m tools.pipeline_eval.qualification.winner_transplant_makeup /path/to/primary/work /path/to/new/makeup/work --plot /path/to/separate/plots`. It reads the sealed primary schedule and launches only cells left unfitted specifically by the primary last-start horizon. [Make-up prediction lock](makeup/prediction-lock.json)
