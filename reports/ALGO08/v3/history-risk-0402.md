# Held DS30-0402 history-risk transfer

Both earlier catalogues were healthy, so the frozen rule selected lean discovery on the original signed 20 ms DS30-0402 packet. The worker exited in **27.243 s wall / 27.179 s CPU**, or **27.655 / 27.590 s** including launcher admission. It reproduced all **4,821 ordered owners per calibration arm** from archived installed v3. The recorded endpoints, grid and position figure differ, with horizontal error changes under **0.05 mm** in both arms. The recording had previously supplied optimizer and salvage development. This transfer held it for the route choice. [Frozen transfer](history-risk-0402-protocol.md) · [Authenticated four-case receipt](measurements/history-risk-four-case.json.gz)

## Measurement and publication

The earlier orbit check used the original three sample times and **1,323** authenticated candidates in each of the two catalogues. Both had zero faults. The check took **40.840 ms CPU** inside inference. The worker made one authenticated common preparation (**2.542 CPU s**) and one inference. The two original signed refits accepted after **2.240 CPU s** combined, within **2.298 s** for qualification and fit. The full numerical solve took **22.710 CPU s**. The ordinary late exterior gate saw interior endpoints and did not need to run a geographic probe. All 48 original causal bodies were resident at admission. The process recorded 832 kernel input blocks and 11 major faults. These counters describe the process as a whole. There was no waveform or backing archive read. [Frozen decision implementation](history_risk_route.py)

| Calibration | Named → routed error | Named → routed conditional RF RMS | Ordered owners per arm |
|---|---:|---:|---:|
| `c = 0` | 863.650648 → 863.650693 m | 100.672203444 → 100.672203450 Hz | 4,821 → 4,821 |
| Fitted `c` | 860.301627 → 860.301640 m | 100.576460190 → 100.576460192 Hz | 4,821 → 4,821 |

There were no lost or added owners, NORAD reassignments or role changes. The original grid and the routed grid each have 179 coordinates and a zero endpoint objective replay difference. They share 81 exact coordinates, with a maximum score difference of **0.315** per arm on those coordinates. The recorded fit path differs. Seven figures match encoded bytes and decoded RGBA pixels. The position figure differs with the changed grid. All eight worker PNGs validate independently at their original dimensions, and both sidecars bind the routed position PNG, terminal and input. [Installed-parity reference](exact-named-0402.md)

## Four-case saved reduction

| Saved process elapsed, s | DS30-0160 | DS30-0316 | DS30-0374 | DS30-0402 |
|---|---:|---:|---:|---:|
| Archived installed v3 child | 15.999 | 18.358 | 28.324 | 73.351 |
| Routed worker through exit | 10.471 | 12.371 | 16.228 | 27.243 |
| Routed launcher admission | 0.415 | 0.440 | 0.436 | 0.413 |
| Routed worker plus admission | 10.886 | 12.811 | 16.664 | 27.655 |
| Paired wall ratio, child | 1.528× | 1.484× | 1.745× | 2.693× |
| Paired wall ratio, admission charged | 1.470× | 1.433× | 1.700× | 2.652× |

| Timing scope versus archived v3 child clocks | Named total s | Routed total s | Summed ratio | Median paired ratio |
|---|---:|---:|---:|---:|
| Elapsed, child clocks | 136.032540 | 66.312516 | 2.051386× | 1.636647× |
| Elapsed, routed admissions charged | 136.032540 | 68.015423 | 2.000025× | 1.584726× |
| CPU, child clocks | 135.867847 | 66.185261 | 2.052841× | 1.637333× |
| CPU, routed admissions charged | 135.867847 | 67.869111 | 2.001910× | 1.586083× |

The charged elapsed sum has **0.847 ms** of headroom against an exact 2× threshold. That margin is too small to establish a repeatable 2× result. The sum depends heavily on the costly archived DS30-0402, where named inference fit three cavity configurations that it ultimately rejected. The new route makes different scientific decisions earlier, so these results do not establish mathematically equivalent inference across the cohort. Archived worker clocks omit their launcher admissions. This analysis omits lock wait and offline scoring from both boundaries. It contains no raw timing or fresh installed control. [Named cavity attribution](named-roster-0402.md) · [Previous three cases](history-risk-0374.md)

Run `history_risk_route_trial.py launch 0402 FRESH_TMPFS_ROOT`, `score 0402 FRESH_TMPFS_ROOT`, and `history_risk_route_panel.py FRESH_TMPFS_ROOT NEW_PANEL.json --case 0402`. The single child used freeze `07b80660f`. The witness is `/dev/shm/leo-v3-history-risk-0402-01`. The uncompressed receipt SHA-256 is `2b7cf61aaabe5aa89ff5396376e229603cb9349dd49d3e37776994b5d2740278`. Five focused tests passed. [Trial](history_risk_route_trial.py) · [Reduction](history_risk_route_panel.py) · [Tests](../../../tests/pipeline_eval/test_history_risk_route.py)
