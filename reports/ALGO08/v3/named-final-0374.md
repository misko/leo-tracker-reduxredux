# Current fast discovery on saved DS30-0374

The current candidate completed the saved process in **19.732 s**, versus **28.324 s** for named ALGO08v3 on the identical receiver packet, a **1.44×** speedup. The named final fit was requested and **neither original calibration arm ran**. The signed-history gate declined it, and the ordinary joint finish reproduced the older DS30-0374 candidate position and RF residuals exactly. The fast route retained **2,822 of 2,905** named owners in each arm. This records both a saved-process gain and an activation limit for the current named-finish composition. [Frozen protocol](named-final-0374-protocol.md) · [Pair receipt](measurements/named-final-0374.json.gz)

## Matched saved-input clocks

| Same signed detector packet | Named v3 | Current candidate |
|---|---:|---:|
| Saved process launch to exit, elapsed / CPU (s) | 28.324 / 28.268 | 19.732 / 19.727 |
| Publication function, elapsed / CPU (s) | 26.805 / 26.751 | 18.151 / 18.147 |
| Numerical solve and grid, elapsed / CPU (s) | 24.061 / 24.006 | 16.093 / 16.090 |
| Complete numerical grid / verified PNGs | 179 / 8 | 179 / 8 |

The processes ran candidate first from the same tmpfs copy of the archived full-20 ms packet. It carries **6,770 issued, 4,644 admitted and 2,126 excluded** stereo visits. The worker used the original 25 km offer, signed inventory and causal archive after one metadata-only handoff. Staging took **0.490 s** outside both clocks. All 47 causal orbit snapshots, **84.0 MB** logical, used **71.5 MB** of distinct digest-verified data already staged in memory. Both processes reported zero input blocks and zero major faults. No original waveform or bulk TLE payload was opened. There was no authenticated saved 20/12 ms mixed arm for this recording, so receiver composition and raw-to-exit speed remain outside this comparison. The earlier saved 24.134 and 19.129 s results use publication-function clocks from a different pair and remain separate. [Earlier signed publication](signed-0374-transfer.md) · [Earlier optimized full catalogue](optimized-full-catalogue.md)

## What ran and what survived

The candidate spent **4.035 CPU s** on the regional proof, **3.960 s** on cold discovery, and **2.979 s** on standard evidence. The proof reached eligible exterior separation after 24 probes, then continued with a regional position fit. Cold discovery sits inside the **6.383 s** pre-evidence candidate work, alongside 0.803 s of initial gates, 0.901 s of salvage, 0.130 s of predictive support and 0.465 s of ordinary finish. Signed qualification added **0.047 s** with future and disjoint-future gains of **−6.645 and −11.772**. It returned the unqualified status before either original final fit. No installed numerical retry ran. The separate renderer used **1.922 CPU s** including four native Cairo orbit figures and two native residual figures. These nested clocks cover distinct stages only where stated. Regional proof, cold catalogue work and numerical evidence remain the largest measured pieces on the active branch.

| Calibration | Named horizontal error | Candidate horizontal error | Named RF RMS | Candidate RF RMS |
|---|---:|---:|---:|---:|
| `c=0` | 1.855441 km | 1.859620 km | 101.535913 Hz | 101.577325 Hz |
| Fitted `c` | 1.935370 km | 1.928706 km | 101.519803 Hz | 101.594246 Hz |

The new stock publication reproduces the archived terminal, both arm values, owner maps and scientific path/grid digests, and all eight encoded and RGBA figure hashes. The candidate gives **+4.178 m fixed and −6.664 m fitted** error changes, with **+0.041 and +0.074 Hz** RF RMS. It keeps the NORAD and role of every shared owner. Both arms lose 25 conditional observations from NORAD 48464, 23 from 59492 and 35 from 66599. All 411 stock predictive owners survive. Its 179-node adaptive grid has 81 coordinates matching the corresponding stock order. Both complete grids have zero objective replay discrepancy in each arm and valid path/grid pointers to their own position figures. The case passes the earlier 250 m per-arm development tolerance and does not establish exact stock scientific parity for the combined option.

The history support was present. The past-distribution gate passed, and the signed correction evaluated 3,370 training, 2,181 future and 432 satellite-disjoint future transitions against a minimum of 30 in each split. The correction chosen on training used squared archive age. It degraded the held score on both scored future sets, so both positive-gain conditions failed before the paid original fit.

A graph-only audit joined all 83 missing IDs to three contiguous stock spans on channel 1. The ordinary route initially rejected all three components, then found salvage offers, and rejected all three again at its second curved gate. Times are elapsed relative to the signed hardware anchor. The receiver numbers use the installed graph's one-based labels.

| Graph component | Stock NORAD | Missing ordered span | Time span (s) | Salvage offer | Missing rows covered by offer |
|---|---:|---:|---:|---:|---:|
| RX1 CH1 T008 | 48464 | Entire track, 25 rows | 19.508–43.265 | `[0,25)` | 25 |
| RX1 CH1 T003 | 59492 | Entire track, 23 rows | 186.521–234.741 | `[0,23)` | 23 |
| RX2 CH1 T001 | 66599 | `[30,65)` of 65 rows | 135.813–174.821 | `[0,32)` | 2 |

The first two tracks need their already proposed spans to survive the joint curved check. The third needs a late-span alternative in the candidate list before that check. Those support differences precede the decision to run the final fit. A policy that runs the original fit on the existing candidate support still starts 83 rows short of the named selection. [Current final-fit controls on other recordings](original-final-fit-transfer.md)

## Reproduce

Use `named_final_0374.py launch NEW_TMPFS_ROOT` under the shared exclusive Gauss lock, CPU 2, nice 15, best-effort I/O priority 7 and one numerical thread. Then run `audit` against that root with the local scoring modules available. The scorer checks the stock publication against the original signed evidence and seals both runs before loading the eligible survey reference. Run `audit-ownership` against the sealed root for the original graph join. That audit performs no position solve. The first isolated launch exited in **0.043 s** during an import, before a numerical worker ran. Only the subsequent pair completed numerical work. Three component tests passed. The uncompressed pair seal SHA-256 is `cc668f4b3aa6506dc7bc1bab74640affafaec87190ae044b0aa9c74f4597eff4`. The graph-only audit SHA-256 is `da7b3c81845eacb4b59ca41232bf3b2ee4a77d42d3461da1a4acbb03495b9e3f`. [Driver](named_final_0374.py) · [Component tests](../../../tests/pipeline_eval/test_named_final_0374.py)
