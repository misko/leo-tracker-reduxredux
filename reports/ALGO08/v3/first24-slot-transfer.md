# Slot transfer and the remaining 2× budget on the first 24 DS30 pairs

The reuse-first DS30-0049 order materially lowers the transferable timing estimate. Across the first 24 pairs it projects **28.266 s less producer CPU**, **16.817 s less acquisition wall time**, or **11.618 s more through-exit wall time**, depending on which measured boundary is transferred. The acquisition and through-exit sensitivities leave **223.732 s** and **252.167 s** to the summed 2× gate. Even removing the entire rejected DS30-0147 proposal with perfect foresight leaves **207.260 s** and **235.695 s**, respectively. These are separate sensitivity calculations on the sealed field clocks. [Frozen model](first24-slot-transfer-protocol.md) · [Case-level receipt](measurements/first24-slot-transfer.json)

The unchanged field baseline is **2,221.777 s installed versus 1,351.438 s candidate**. The observed summed and paired median speedups were **1.644× / 1.739×**, with **240.549 s** above half the installed total. Candidate wall partitions into 847.842 s acquisition, 464.329 s decision and publication and 39.267 s other work. Acquisition includes 383.866 s in native callbacks. Normal prefetch served all **1,829** requested buffers, **142.784 GB** of 164.670 GB of original payload, and consumed 234.756 worker CPU seconds. Its 50.951 s of exposed demand waiting already belongs to acquisition. [Fixed workload and disjoint bounds](measurements/first24-slot-transfer.json)

## Donor boundaries

All entries below are actual ordinary-minus-reuse differences in seconds. The DS30-0016 receiver hook consumed its full resident 808 visits and used syscall tracing and an earlier 20/8 native packet. DS30-0049 used the frozen field sparse receiver and slot port on the first 384 visits with a separate prefix authority. Both timed fresh processes, the real producer and the authenticated raw detector; their published numeric and image work was outside this boundary. The reuse arms hit seven reused destinations out of 11 on DS30-0016 and two out of five on DS30-0049. [Complete receiver-hook donor](prefetch-snapshot-accounting.md) · [Field-receiver prefix donor](prefetch-prefix-0049.md)

| Donor and launch order | Original / prefetched bytes | Producer CPU Δ (s) | Acquisition wall Δ (s) | Raw exit wall Δ (s) |
| --- | ---: | ---: | ---: | ---: |
| 0016 ordinary first | 991,734,597 / 834,805,982 | +1.006852 | +1.376231 | +1.427030 |
| 0016 reuse first | 991,734,597 / 834,805,982 | +0.797363 | +0.627097 | +0.627204 |
| 0049 ordinary first | 468,486,497 / 390,491,856 | +0.476879 | +0.459301 | +0.517149 |
| 0049 reuse first | 468,486,497 / 390,491,856 | +0.077302 | +0.045992 | **−0.031773** |

All enrolled waveform pages were resident across the donors. DS30-0016 ordinary first still charged 14,472 process-wide input blocks and 29 major faults, and exposed 165.592 ms prefetch demand wait against 0.064 ms for reuse. Both DS30-0049 first processes charged unattributed process-wide I/O, 8,912 blocks and 28 major faults on ordinary first, and 10,144 blocks and 47 faults on reuse first. Its second processes and checked original-member authentication envelopes charged zero input blocks. The trials identify a worker CPU direction on both recordings with variable magnitude. The whole wall deltas also include differences in the process before and after the producer. [Per-arm donor counters](measurements/first24-slot-transfer.json)

## Independent field projections, with both fallback calls retained

Each cell below gives the **summed / paired median wall speedup**, followed by seconds above half the installed total. Positive producer credit is capped at actual paid worker CPU. Positive wall credits are limited to their own paid non-detector scope. The raw exit cap excludes decision/publication and independent verification. The CPU cap binds only on DS30-0102 in the two ordinary-first CPU sensitivities, removing 15–16 ms from each aggregate. No positive literal wall credit reaches a cap. Zero-hit DS30-0107 remains unchanged, and the measured slower 0049 exit retains its negative sign through scaling. The CPU-as-wall column assumes every removed worker CPU second translates to a wall second. The two literal wall columns each transfer the whole signed measured difference at that boundary independently. [Formula and case-level credits](measurements/first24-slot-transfer.json)

| Donor order | Producer CPU attributed to wall | Acquisition wall transfer | Raw exit wall transfer |
| --- | ---: | ---: | ---: |
| 0016 ordinary first | 1.884 / 1.983×, **+68.353 s** | 1.991 / 2.100×, **+5.160 s** | 2.006 / 2.118×, **−3.529 s** |
| 0016 reuse first | 1.829 / 1.927×, **+104.169 s** | 1.786 / 1.883×, **+133.291 s** | 1.786 / 1.883×, **+133.273 s** |
| 0049 ordinary first | 1.887 / 1.987×, **+66.193 s** | 1.877 / 1.976×, **+72.604 s** | 1.911 / 2.013×, **+51.452 s** |
| 0049 reuse first | 1.679 / 1.775×, **+212.284 s** | 1.665 / 1.760×, **+223.732 s** | 1.630 / 1.724×, **+252.167 s** |

The old 1.828–1.884× summed estimate is the 0016 producer-CPU-to-wall sensitivity. The independent 0049 reuse-first observation supports much less credit. The sole slots-only row clearing both 2× gates transfers the entire 0016 ordinary-first exit difference, including the larger nonproducer differences in that order. Its reciprocal order and 0049 do not reproduce that wall result. With actual CPU denominators and fallback costs retained, the modeled summed CPU speedups are **1.811, 1.753, 1.815 and 1.598×** in table order. [Both timing gates for wall and CPU](measurements/first24-slot-transfer.json)

## Disjoint fallback and common-path budget

DS30-0147 is the only timed lean rejection. Its failed proposal cost **16.472 wall / 16.206 CPU s**. The accepted named fallback separately cost **59.334 wall / 59.094 CPU s**. Their disjoint 75.806 wall seconds are inside the actual 79.192 s solve. Perfect foresight to skip the proposal preserves the named solve's measured cost. Giving away that named solve is an upper bound that assumes its accepted fix for free. [Paid solver route accounting](field-fallback-budget.md)

| 0049 reuse-first model | Fallback treatment | Summed / paired median wall speedup | Remaining summed gap | Additional common-path reduction for both gates |
| --- | --- | ---: | ---: | ---: |
| Acquisition wall | Keep actual costs | 1.665 / 1.760× | 223.732 s | 18.35% |
| Acquisition wall | Skip rejected proposal | 1.685 / 1.760× | 207.260 s | 16.99% |
| Acquisition wall | Free named fallback | 1.742 / 1.773× | 164.398 s | 13.48% |
| Acquisition wall | Both free | 1.765 / 1.773× | 147.926 s | 12.13% |
| Raw exit wall | Keep actual costs | 1.630 / 1.724× | 252.167 s | 20.40% |
| Raw exit wall | Skip rejected proposal | 1.650 / 1.724× | 235.695 s | 19.06% |
| Raw exit wall | Free named fallback | 1.704 / 1.735× | 192.833 s | 15.60% |
| Raw exit wall | Both free | 1.726 / 1.735× | 176.361 s | 14.26% |

The common pool includes the measured acquisition and decision/publication phases, removes both 0147 calls and any positive modeled slot credit, and excludes startup and independent checking. With no slot credit its 1,236.365 s would need **19.46%** less time to clear both gates with actual fallback, or **18.12%** with perfect rejection foresight. The summed gate binds on every 0049 reuse-first row. The machine receipt preserves both required fractions separately for other scenarios. For example, crediting the 0049 ordinary-first acquisition model and both free 0147 calls clears the sum while still requiring another **2.706 s** of matched common work for the median. The independently measured evidence therefore leaves most of the required speed work on paths shared by many original recordings. [Complete controls and constraints](measurements/first24-slot-transfer.json)

The specification froze at `d06389cc0` and the scored implementation at `4d6b39bf0`. Three tests cover signed caps, stage separation and the paired median constraint. Reproduce from the pinned metadata paths using the existing read-only NVMe ledger. [Reducer](first24_slot_transfer.py)

```sh
snapshot=/srv/postgres-nvme/leo-ds30-research-worktrees/field-fallback-first24.gPoQpoNE
campaign=/srv/postgres-nvme/leo-ds30-evaluation-20261124
sudo -n -u leo env PYTHONPATH="$PWD" python3 -B \
  -m reports.ALGO08.v3.first24_slot_transfer "$snapshot" "$campaign"
```
