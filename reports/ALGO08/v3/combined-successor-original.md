# Original-file verification of the guarded successor

The complete verified-once receiver and guarded successor completed the two original physical recordings in **8.464 s wall / 8.436 s CPU**. Installed ALGO08v3 took **12.242 / 12.238 s** on those recordings. Both reproduced a positive fix on DS30-0016 and the original withholding on DS30-0107. The elapsed speedups were **1.446× summed and 1.764× at the paired median**. The median cleared 1.6×, the sum missed it by **0.813 s**, and both 2× gates failed. [Frozen protocol](combined-successor-original-protocol.md) · [Sealed process and scientific evidence](measurements/combined-successor-original.json.gz)

| Original recording | Installed v3 wall / CPU | Prior verified once wall / CPU | Guarded successor wall / CPU |
|---|---:|---:|---:|
| DS30-0016, complete | 10.744677 / 10.742462 s | 8.047974 / 8.046283 s | **7.862243 / 7.859794 s** |
| DS30-0107, withheld | 1.497018 / 1.495600 s | 0.527095 / 0.525004 s | **0.601460 / 0.576044 s** |
| Sum | 12.241696 / 12.238062 s | 8.575069 / 8.571287 s | **8.463703 / 8.435838 s** |

Each candidate clock begins at child launch and ends after standard publication verification and exit. The prior verified-once and named controls are separately archived one-run measurements. The CPU ratios were **1.451× summed and 1.791× median** against v3, with the same pass pattern as wall time. The wall sum needs **2.343 s** more to reach 2×. The candidate was **0.111 s** faster by wall sum than the prior verified-once pipeline. [Prior same-original controls](legacy-verify-original.md)

## What ran

The positive acquisition took **3.015 s** versus **3.514 s** earlier. It kept 11 lookahead submissions and hits covering **834,805,982 bytes**, with zero lookahead fallback. Lookahead worker CPU varied from **0.627 to 0.169 s** on that same input and reader. The updated positive solve took **2.179 s** versus **1.924 s**, and standard rendering took **0.895 versus 0.890 s**. The 0.186 s positive process gain occurred outside the solver. The original input and verified-once reader algorithm were identical and this observation supplies no isolated acquisition or solver speedup estimate.

The three curved components on DS30-0016 could not support the bilateral two-centre scout. The candidate ran the ordinary four-centre order, discarded the tentative result as a checkpoint source, and reranked ordinarily under the exact producer. That conservative retry paid **121.0 ms CPU**. Cold discovery was **0.304 s wall**, versus 0.179 s earlier. The two ordinary ranked finalists produced two exact checkpoints, with no named fallback or checkpoint consumption. One live orbit scope executed without adding knots or repeating inference. This raw route omitted the earlier causal election because its captured regional alias can bypass live orbit capture. [Combined saved implementation](combined-successor-0289.md)

The qualified native grid executed **708 projections, 356 selected designs and 356 design fills**, with four exact projection and two exact template comparisons. It sampled all **179** matched grid nodes in **0.178 CPU s**, with zero reported per-kernel fallback. That grid was already active in the prior verified-once control. The 0107 receiver proved the ordinary empty-curvature terminal and never entered any of these solver or rendering hooks.

## Scientific output

DS30-0016 authenticated all **13 members**, **991,734,597 encoded bytes** and **1,292,800,000 decoded bytes**. It retained the original **808 issued and 713 admitted visits** and their exact signed packet, with 93 full-anchor and 620 short stereo visits. The original terminal remained an interior fix with no geographic withholding or exterior scoring. The official outputs matched the prior verified-once control, including both coordinates, 115 ordered owners per arm, complete grid and path, and all eight PNG byte and decoded RGBA hashes. Both numerical sidecars pointed to the verified position image. [Original region and installed location results](history-risk-physical-cohort.md)

| Calibration | Successor horizontal error | Installed v3 horizontal error | Successor conditional RF RMS | Successor all-owned RF RMS |
|---|---:|---:|---:|---:|
| Fixed zero | 490 m | 1,644 m | 134.021487 Hz | 135.546968 Hz |
| Fitted | 980 m | 1,661 m | 133.739967 Hz | 136.859291 Hz |

DS30-0107 authenticated its whole original partial/empty-containing member, **33,519,983 encoded bytes** and **44,294,856 decoded bytes**. All 29 issued visits, 27 valid stereo visits, 54 radio opportunities and 19 factors match the original signed replay. The actual terminal remained `no_active_curvature`. Both arms have null position and RF, with no owners, PNGs, grid or path. The positive and withholding are development evidence for the composition.

## Admission, startup and reproduction

The two successful runs used the same already sealed private read-only binds, the original causal archive and lookahead, the same artifact hashes, the shared Gauss lock, CPU 2, nice 15, I/O priority 7 and one numerical thread. All **242,675** positive source pages and **8,205** withholding source pages were resident before and after their measured children. There was no conditioning, new RF, prior replay-map use or backing waveform read. The positive process charged 104 input blocks and the withholding zero. Both recorded zero major faults.

Controller checks cost **1.306 / 1.302 wall s** for positive / withholding. The separate waveform-denied scanner, lookahead and solver startup probes cost **1.181 / 1.319 wall s**. The probe CPU field measures the controller only. Charging admission and probes to the two candidate workers produces **13.572 s wall** before the earlier reusable native artifacts. The prior artifact build took **0.350 s wall / 0.325 s compiler CPU**. Each genuine worker also paid its own normal in-process setup inside the table clocks.

An initial candidate process spent **0.371 wall / 0.369 CPU s** and exited before inventory or acquisition on a missing sparse-checkout lookahead source. Its preceding admission cost 1.305 s and scanner/solver startup probe 1.107 s. The frozen recovery materialized the three existing source files and extended the waveform-denied probe to invoke the actual lookahead loader. The failed child opened no waveform or detector opportunity and is retained separately in the receipt. No completed original acquisition was repeated.

Run `combined_successor_original.py launch FRESH_TMPFS_ROOT DS30-0016` from the installed interpreter and the documented private read-only mount under the shared lock, then `score` using the research read-only storage modules. The launcher admits the one DS30-0107 child only after the same positive output verifies and its clock is strictly below the archived 8.047974 s. The complete executions ran source `8c32712a8`. Fourteen component tests passed. The combined uncompressed receipt SHA-256 is `7906604baa73d0c94dec2f95ca82974a0e78a47b62079b73eb66a04900fe23b6`. [Launcher and gate](combined_successor_original.py) · [Raw solver entry](combined_successor_raw_entry.py) · [Private mount pattern](history-risk-0016-raw.md) · [Tests](../../../tests/pipeline_eval/test_combined_successor_original.py)
