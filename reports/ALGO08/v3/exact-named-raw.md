# The native 20/8 ms receiver feeding exact named localization

One fresh process used the complete resident North simulation to run the native all-visit 20/8 ms receiver, select one authenticated held-history packet and execute the exact named solver under the original 25 km containing offer. It completed in **15.561 s**, versus **19.967 s** for the instrumented installed ALGO08v3 control, a **1.283×** wall-clock ratio. Both published complete standard grids and eight PNGs. North is a previously scored simulation. The only physical raw run in this comparison was the independently staged DS30-0107 withholding control. [Frozen protocol](exact-named-raw-protocol.md) · [Receipts](measurements/exact-named-raw.json.gz)

| Actual North clocks | Installed ALGO08v3, wall / CPU s | 20/8 ms and exact named, wall / CPU s |
| --- | ---: | ---: |
| Fresh process through verified exit | 19.967 / 19.946 | 15.561 / 15.555 |
| Authenticated raw receiver | 9.507 / 9.503 | 6.144 / 6.143 |
| Held-history selection | — | 0.071 / 0.071 |
| Named numerical solve, including full grid | 7.172 / 7.163 | 6.082 / 6.080 |
| Eight-figure render | 1.698 / 1.691 | 1.649 / 1.648 |
| Actual installed publication call | 19.357 / 19.338 | 8.074 / 8.072 |
| Additional post-publication verification | 0.378 / 0.378 | 0.011 / 0.011 |

The original named publication call includes its receiver. The candidate's installed publication call begins after acquisition, selection and activation setup. Candidate decision and publication took 8.817 wall / 8.814 CPU s, including its earlier guard, setup and verification. The renderer and solve rows are nested within publication scopes. The candidate decoded all eight PNGs on their installed verified read and reused those results for its audit. The named control decoded the eight after publication. The independent earlier named North run took 16.133 s through exit and verified its science outside that clock. The new pair measures one instrumented run per arm. [Previous named raw control](measurements/current-north-control.json.gz)

The two original waveform traversals used the same 1,200 visits and 2,400 radio opportunities, with 385,609 compressed payload pages and 188 index pages fully resident throughout. They emitted 456 authenticated signed factors each, reproducing their independently archived same-recipe packet digests. The candidate paid 304 full and 2,096 native short radio calls, emitted 1,595 preselector factors, selected 456 and paid zero tail refinements. It handed off the packet once. Both named fits ran once. The candidate checked the original causal archive, used exact regional prep and completed its ordinary exterior proof. Its portable index transfer used a producer earlier than the signed North cutoff, validated and loaded the snapshot in 1.689 ms, and used 11 preindexed and 12 cold bodies. The earlier independent index build cost 4.320 s, outside this both-resident pair. Charging that build once before this candidate would yield 19.881 s by addition, a planning estimate. Stable compact ranking handled 272 calls. The constrained prepared gates and previous-bank recovery did not fire.

| Arm | Installed error | Candidate error | Installed RF RMS | Candidate RF RMS |
| --- | ---: | ---: | ---: | ---: |
| Fixed zero | 105.69 m | 111.95 m | 9.70 Hz | 44.98 Hz |
| Fitted | 140.78 m | 128.09 m | 18.57 Hz | 50.42 Hz |

The fitted arm improved localization error by 12.69 m and the fixed arm worsened by 6.26 m. Both residual RMS values worsened. Each candidate arm retained all 302 named observation IDs and assigned 40 more. Seventeen common roles changed and the common satellite identities were preserved. Each publication kept the original clipped 137-point, matched-calibration full layout, compared with up to 179 points when the offer admits the full grid. All eight figures have the same dimensions and standard names. Each grid and path binds its own terminal, native packet and position PNG. No evaluation location entered either run.

The saved far-omitted North control consumed that same authenticated 20/8 packet exactly once, with zero waveform reads, in **8.979 s** through exit. The supplied offer omitted the scoring reference by 52.5 km. The same ordinary named numerical port withheld with `both_receivers_support_far_exterior`, as did the archived named far control, with both positions and RF RMS null. It published zero PNGs or position sidecars.

The identical raw entry withheld independently on complete physical DS30-0107 in **0.577 wall / 0.573 CPU s**. Its 29 issued and 27 valid visits produced the same 19 verified observations, native digest, graph proof and signed terminal as the earlier 20/8 run. The longest candidate lane was 0.708 s against the 20 s minimum. Both arms had null positions and RF RMS, with no numerical ports, grids, paths or PNGs. All 8,184 original compressed and 20 index pages stayed resident in the private read-only tmpfs mapping. The prior installed named result took 1.406 s, a 2.44× ratio to this separate candidate run. The physical candidate ran without needing a portable index.

For a split reader alone to bring the measured North candidate to 1.6× or 2× versus the fresh named control, it would have to save 3.082 s or 5.578 s respectively. The full and short native calls already consumed 3.153 CPU s within the 6.144 s acquisition. On one core, even granting free decoding, I/O, hashing, scheduling and all other acquisition work would save at most 2.991 s with comparable remaining costs. Using the native elapsed floor of 3.230 s tightens the cap to 2.914 s. The CPU floor caps the whole speed ratio at 1.5885×. The trial skipped a new North derivative conversion. This ceiling applies to the measured North workload and boundary.

The first launcher preflight failed before a child ran. Two earlier named children stopped before acquisition after isolated Python import and repeated startup checks, consuming 0.046 and 1.169 wall s respectively. Their clocks are separate in the receipt. The post-run compatibility fix restores the existing default path validator lookup for saved callers. The measured raw entry supplied its validator explicitly. Nineteen focused and adjacent tests passed.

## Reproduce

Run the [North driver](exact_named_raw_transfer.py) and [scorer](exact_named_raw_score.py) under the original shared low-priority Gauss lock, CPU 2 and single-thread configuration. The benchmark inputs and full evaluated argument vectors are in the receipt. `exact_named_raw.py` takes the signed archive digest, actual staged recording, staged archive, supplied region, a fresh output directory and the reviewed native library paths. The three portable index options are optional. The stage guard requires tmpfs mounts and accepts canonical read-only private binds. [Raw entry](exact_named_raw.py) · [Physical withholding driver](exact_named_raw_withhold.py)
