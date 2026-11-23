# What restoring omitted owner lanes buys on the alternating mask

Restoring all omitted lanes that the full mixed receiver's two calibration arms originally owned reversed the dense saved-position regression. DS30-0008 horizontal error fell from **2.213 to 0.704 km** at `c=0` and **2.077 to 0.661 km** with fitted `c`. Both RF RMS values rose. Reopening the 1,452 dense lanes would spend **1.550 CPU s** of the alternating mask's 4.735 s gross native saving, leaving **3.185 CPU s** before any cost to identify them. Full-output ownership is only available after running the complete receiver and solver. This saved counterfactual prices a hindsight ceiling. [Frozen protocol](target-owner-recovery-protocol.md) · [Sealed receiver and publication evidence](measurements/target-owner-recovery.json.gz)

| Original mixed receiver | DS30-0016 | DS30-0008 |
|---|---:|---:|
| Issued / admitted stereo visits | 808 / 713 | 6,772 / 6,765 |
| Original owned observations, union of both c arms | 116 | 4,367 |
| Target-omitted short lanes | 463 | 4,435 |
| Target-omitted lanes with a positive factor | 145 | 2,414 |
| Original owner lanes to reopen | 37 | 1,452 |
| Remaining omitted short lanes | 426 | 2,983 |
| Gross target native saving | 0.480 CPU s | 4.735 CPU s |
| Billed reopened calls | 0.038 CPU s | 1.550 CPU s |
| Remaining native saving | 0.441 CPU s | 3.185 CPU s |

The two full arms share every selected observation ID, NORAD and role in each recording. The census therefore reopens the same lanes as either arm alone. Each reopened lane contains one original signed factor. The recordings supplied aggregate native CPU and counts over **1,240** weak and **11,834** dense short-primary calls. There are no individual call clocks. The price uses the corresponding 1.036 and 1.068 ms mean for every reopened and omitted lane. The projected dense saving exceeds the earlier 2.735 s receiver gap by 0.450 s and falls short of the 4.616 s gap by 1.431 s. The model keeps every full anchor and the original authentication, read and decode costs. It leaves 108 weak and 962 dense omitted positive factors outside the owner union, in addition to the original empty omissions. [Target mask budget](receiver-mask-budget.md)

The 37 weak reopenings all fall on radio 0 and three original Graph tracks, with 15, 14 and 8 observations. Two satellites account for 23 and 14 of the reopenings. They span issued visits 48–803 and occupy all ten fixed chronological deciles. The 1,452 dense reopenings split 812/640 across radios 0/1, span issued visits 28–6758 and occupy every decile with **112–172** observations. They occupy **123 of 208** original Graph tracks across **27 satellites**. The five biggest tracks account for 159 of 1,452 rows, and the five biggest satellite groups account for 704. Every reopened row joins uniquely to the original released Graph. The dense burden is distributed over much of the recording. [Plan and graph validation](target_owner_recovery.py)

## Dense saved publication

| Detector packet | `c=0` error | Fitted `c` error | `c=0` RF RMS | Fitted `c` RF RMS |
|---|---:|---:|---:|---:|
| Named 20 ms v3 | 1.639 km | 1.512 km | 129.703 Hz | 129.663 Hz |
| Full mixed 20/12 ms | 0.919 km | 0.857 km | 140.961 Hz | 140.950 Hz |
| Alternating target | 2.213 km | 2.077 km | 138.989 Hz | 138.932 Hz |
| Target plus reopened owner lanes | 0.704 km | 0.661 km | 143.620 Hz | 143.496 Hz |

The saved oracle packet contained all 4,367 full-owner factors, but the reconstructed solver assigned 4,426 observations in each arm. Relative to the complete-input fit, it shared 4,190 original IDs, omitted 177, added 236, changed NORAD on 18 shared observations and changed role on 52. It selected 1,399 of the 1,452 reopened factors. Relative to the alternating target it retained 2,693 IDs and added 1,733. All changes are the same in both calibrations. The oracle restored measurements and then allowed ordinary graph construction and inference to choose owners independently. [Complete owner comparison](measurements/target-owner-recovery.json.gz)

One fresh saved process completed in **28.887 s wall and 28.851 CPU s**. Its numerical solve took **24.173 CPU s**, including 1.305 s in the observed Graph call. The earlier target job took 29.622 s wall and 29.147 CPU s, with 24.618 CPU s in the solve. The earlier full mixed solve took 26.105 CPU s. These are historical controls from separate launches. Combining modeled acquisition CPU and observed saved solve CPU gives 58.508 s for complete mixed, 52.286 s for target and 53.392 s after reopening. This illustrative sum excludes remaining publication costs and any method for finding the omitted owners. The saved job used the earlier target's stock Graph, regional proof, optimized joint solver and standard renderer. It verified both calibration fixes, a completed 179-point grid, both sidecars bound to their own position PNG, and all eight encoded and decoded PNGs. [Saved execution and verification](target_owner_recovery_trial.py)

The saved packet preserves every original radio probe, measured factor byte and delivery clock in native order. It has a distinct saved-only receiver digest bound to the original parent, target mask, full owner receipt and exact reopened lanes. Selection, graph census and staging charged 2.921 CPU s outside the candidate process. The one candidate ran on the shared low-priority Gauss core and exited 0 with zero input blocks. It used the previously staged tmpfs orbit archive, region and authenticated inventory. No raw receiver call or second saved solve was made. Reproduction artifacts remain in `/dev/shm/leo-v3-target-owner-recovery-01`. The receiver timing calculation and the dense saved position comparison do not qualify a live schedule. [Focused tests](../../../tests/pipeline_eval/test_target_owner_recovery.py)
