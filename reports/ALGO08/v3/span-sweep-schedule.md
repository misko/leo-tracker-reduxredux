# Span-first stereo sweeps have no detector work to skip with protected continuation

Both the one-third and one-half checkpoints paid every admitted stereo visit on physical DS30-0008 and DS30-0016. Keeping the released continuation on every original 20 ms anchor already requires **6,728 of 6,765 dense visits and 688 of 713 weak visits** before adding a single span-first block. All remaining visits are after the final anchor on their own RF stream, and the frozen terminal blocks buy every one. The tested schedules omit **zero short calls, zero source bytes and zero decoded bytes**. They offer zero acquisition credit before scheduling and buffering. [Frozen protocol](span-sweep-schedule-protocol.md) · [Measured ledger and original clock bindings](measurements/span-sweep-schedule.json.gz)

## Schedule and continuation

DS30-0008 has 6,772 issued windows, the median of the 455-recording DS30 manifest. DS30-0016 has 808 issued windows with more RF exclusions and much sparser owner support. Each case has a completely saved unfiltered 20/12 ms receiver ledger. On both timelines the admitted slots follow channels 1–8 by issued index, with one original actual RF per channel and matching stereo clocks. The rule buys blocks of eight complete RF sweeps, starting with the first and last full block and bisecting the largest remaining gap. Both the chronological comparison and span-first policy preserve the partial tail and all original anchors. After selecting the core blocks, the planner adds complete stereo context from the most recent twelve admitted visits per receiver/channel/RF within eight seconds. Order for buying science blocks and original order for continuation are independent. [Metadata audit](span_sweep_schedule.py) · [Released continuation](../../../tools/pipeline_eval/variants/carrier_continuation.py)

| Recording | Full blocks / partial slots | Admitted visits | Full anchors | Visits paid for anchor history alone | Short lane calls remaining after anchor history | Short lane calls remaining at either span stop |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DS30-0008 | 105 / 52 | 6,765 | 848 | 6,728 | 74 | 0 |
| DS30-0016 | 12 / 40 | 713 | 93 | 688 | 50 | 0 |

The anchor cadence is one every eight admitted visits on an RF stream. In these recordings every earlier nonanchor is in the paid lookback of at least one subsequent anchor. The release stores each measured candidate tuple even if the continuation rule discards it, so direct predecessor closure preserves the exact votes at protected visits without recursively buying older evidence. The audit verified each protected preference, continuation choice and vote list. It allowed context at individual stereo visits, a favorable cost relative to rounding context to whole sweeps. Even the equal-core-count chronological comparison pays all visits at both checkpoints after context. Exact preservation here is for the saved single-exported-factor 20/12 receiver and released history. These measurements do not price the live 20/8 route's held-cycle decision or reveal unexported ranks in named v3. [Genuine receiver and ownership controls](whole-stereo-blocks.md)

## Span alone changes coverage and support

The one-third span core reduces the widest gap between sampled core visits from **198.49 to 8.55 s** on DS30-0008 and from **22.72 to 11.38 s** on DS30-0016. Both core policies span the full hardware interval because they share the terminal remainder. The span-first core plus full anchors, with the context buy disabled, would omit 7,834 dense and 786 weak short lane calls. Submitting those empty slots to released continuation removes support on paid visits as well as on unbought visits.

| One-third, full anchors and no context | Dense span | Dense chronological | Weak span | Weak chronological |
| --- | ---: | ---: | ---: | ---: |
| Measured factors exposed | 3,084 | 3,228 | 223 | 222 |
| Directly omitted previously selected history rows | 3,492 | 3,316 | 205 | 212 |
| Paid protected history choices changed | 1,564 | 509 | 82 | 46 |
| Original owners exposed, `c = 0` | 1,845 / 4,367 | 1,985 / 4,367 | 47 / 116 | 45 / 116 |
| Original owners exposed, fitted `c` | 1,845 / 4,367 | 1,985 / 4,367 | 47 / 116 | 45 / 116 |
| Gross short-call credit at original mean CPU | 8.364 s | 8.364 s | 0.774 s | 0.772 s |

At one-half, the unprotected span-first schedule exposes 2,526 of 4,367 and 63 of 116 owners per arm and changes 1,319 and 75 protected continuation choices. Full context gives complete exposure at both evaluated stops. Owners come from the two original unfiltered published solutions and were joined only after freezing all plans. Owner exposure describes which original input factors remain available. There are no newly fitted coordinates, fitted RF residuals or geographic decisions. An unprotected schedule that discards whole intervals would need its own scientific qualification. Earlier physical end-arc selection already lost the weak fix and moved both DS30-0374 arms by more than four kilometres. [End-arc comparison](../single-core-2x/channel-schedules.md) · [Information-ranked solver warm starts](visit-information-warm-start.md)

## Disjoint acquisition costs on the original layout

| Historical whole 20/12 acquisition | Dense DS30-0008 | Weak DS30-0016 |
| --- | ---: | ---: |
| Original verified members | 106 | 13 |
| Compressed bytes read and authenticated | 8,182,000,357 | 991,734,597 |
| Signed index and manifest bytes | 18,392,998 | 2,199,084 |
| Decoded bytes per-window and whole-member verified | 10,835,200,000 | 1,292,800,000 |
| Full anchor CPU | 4.716 s | 0.427 s |
| All short-primary CPU | 12.635 s | 1.221 s |
| Other acquisition CPU, including reader and proof | 15.053 s | 1.805 s |
| Total acquisition CPU / elapsed | 32.403 / 60.449 s | 3.453 / 3.453 s |
| Anchor-history-only gross short credit at original mean | 0.079 s | 0.049 s |
| Gross short credit at either frozen span stop | 0.000 s | 0.000 s |

The standard reader still authenticates every encoded member, each decoded window and the original whole decoded member. Skipped calls cannot reduce those coverage obligations. The anchor-only CPU estimate uses the original mean of the 11,834 and 1,240 measured short lane calls. Individual omitted call times are unavailable. The historical short stage as a whole is the ceiling for any policy that only removes short detector calls; the complete call counts at the frozen stops give an exact zero count to omit for the tested closure. A looser unprotected one-third pass followed by full fallback would need to retain up to **3.760 GB / 377.28 MB** of original short-prefix samples for the omitted dense/weak lanes, or revisit the reader, and then recompute chronological selection. The favorable model pays the union once and already fails with protection, before charging these costs. A seekable independently authenticated derivative changes the reader contract and is outside this original-layout budget. [Original byte and hash coverage](authenticated-input-coverage.md) · [Separate seekable reader](visit-frame-raw-0016.md)

The saved assay ran once on Gauss CPU 2, with the shared exclusive lock, nice 15, best-effort I/O priority 7 and one numeric thread. It took 1.066 CPU / 1.067 elapsed seconds inside the ledger worker and called no waveform reader, catalogue reader or position solver. The worker wrote the metadata plan before accessing owners or using candidate fields. The plan has SHA-256 `1e7c01039040cf29f25fa3dcd60f8d1edb6e19207bb56babc43c89b938d81617`. The receipt binds both native ledgers, terminal and owner receipts, acquisition evidence, continuation source and protocol. Four focused component tests passed.
