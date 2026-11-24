# DS30-0316 accepts lean with the handoff enabled

The one saved opt-in worker reproduced the matched DS30-0316 history-risk result and exited in **12.246 s**, versus **12.371 s** for the earlier same-input worker. It captured **six ranked nodes and three two-round checkpoints**, then accepted the lean result. Named fallback never ran, so the capture saved no repeated nomination work. The complete comparison measures separate slots and a changed rank producer. The 0.125 s wall difference does not measure a handoff saving. [Frozen protocol](nomination-handoff-0316-protocol.md) · [Sealed result](measurements/nomination-handoff-0316.json)

| Saved comparison | Through-exit wall / CPU | Measured admission wall / CPU | Child plus admission wall / CPU |
| --- | ---: | ---: | ---: |
| Earlier matched history-risk worker | 12.371 / 12.352 s | 0.440 / 0.435 s | 12.811 / 12.787 s |
| Handoff-enabled worker | **12.246 / 12.237 s** | **0.378 / 0.376 s** | **12.624 / 12.613 s** |
| Historical installed ALGO08v3 | 18.358 / 18.353 s | Outside the reported clock | — |
| Historical exact-ports named comparison | 16.887 / 16.829 s | Outside the reported clock | — |

The new worker used the exact earlier signed 20 ms packet, original 25 km offer, ordinary renderer and font cache, and the same earlier portable artifact. All **46 original snapshots, 82,186,082 logical bytes** were resident on tmpfs at launch. It ran alone under the Gauss lock on CPU 2 with nice 15, I/O priority 7 and one numerical thread. It performed one preparation and solve. The new worker reported 200 input blocks and one major fault. The earlier comparison recorded 104 and two. These are process counters, and the measurement does not attribute the blocks to a particular dependency. No original waveform, backing catalogue, alternate region or new baseline worker was read or run. [Earlier accepted route](history-risk-route.md) · [Wrapper binding and scorer](nomination_handoff_0316.py)

## What the candidate paid

The exact grouped producer took **1.322047 CPU s**. Its 624 profiled curve requests all used the compact comparison, preserving the six ranked nodes. The geometry fingerprint took **10.282 ms CPU** and the rank and checkpoint copies took **2.818 ms CPU**. The three ordered two-round scores reproduced the control exactly. There were **zero** scan, rank or prefix reuses. The original signed-survivor finish accepted.

The cold stage took **1.761 versus 2.192 CPU s**, including the newly grouped producer. Total pre-evidence CPU was **3.865 versus 4.067 s**. These are nested clocks. The separate orbit-preparation stage also varied, **2.238 versus 2.452 CPU s** with the same producer, 40 cold bodies, 130 verified reads, 232,250,492 bytes and no portable sidecar hits in either run. The older worker did not record a disjoint clock for the original cold rank. A previous same-input rank-only pair placed the grouped producer's observed benefit at 0.113 CPU seconds under that other clock, and the new full worker paid a different realized group time. The current case confirms the producer and capture obligations on acceptance. It does not establish their net cost across accepting captures or generalize DS30-0004's fallback saving. [Saved chronology and isolated rank pair](nomination-handoff-transfer.md)

## Scientific output

Both history-risk workers published identical calibrated positions, conditional signed RF RMS, and **2,002 ordered observation-owner-role rows per arm**. The exact objective and numerical path and grid science matched. Both standard grids contained all **179 points**, and each path and grid pointed to its verified position figure. All eight PNG files and decoded pixels matched.

| Both matched history-risk outputs | Fixed `c = 0` | Fitted `c` |
| --- | ---: | ---: |
| Horizontal error to the enrolled operator reference | 1.916770 km | 1.833652 km |
| Conditional signed RF RMS | 99.594003 Hz | 99.435320 Hz |

The archived installed named fix has respective horizontal errors of 1.944726 and 1.863056 km and conditional RF RMS of 99.232102 and 99.054093 Hz. On this input the routed branch improves the enrolled geographic score while increasing conditional RF RMS relative to named. The handoff leaves that earlier route comparison unchanged. All nine publication parity checks and seven route and coverage checks passed. Five focused audit and runner tests passed. No second candidate ran.

The as-run freeze is `f2e5ab4ab`, with live files at `/dev/shm/leo-v3-nomination-handoff-0316-01`. The full result SHA-256 is `f7bc212aaddb1c2bbafc5c01532ed0ffaeccf188fcb4284cc8244dbb07c15a5d`.
