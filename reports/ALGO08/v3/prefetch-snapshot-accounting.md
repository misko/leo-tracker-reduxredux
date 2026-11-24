# Kernel copy and destination faults in original lookahead

Two reusable private destinations lowered prefetch worker CPU from **1.658 to 0.651 s** and **1.395 to 0.598 s** in two opposite fresh-process orders on the complete resident DS30-0016 original. Every child covered the same signed **808 visits, 13 members and 991,734,597 encoded bytes** and emitted byte-identical native detections through the normal asynchronous receiver path. Both fresh controls reproduced high worker CPU per byte while the source was resident. The difference was almost entirely charged to `readv` system CPU, alongside fewer destination faults. The trial stopped at detector publication. [Frozen protocol](prefetch-snapshot-protocol.md) · [Measured resident trial](measurements/prefetch-snapshot-0016.json.gz) · [Campaign receipt audit](measurements/prefetch-archive-accounting.json)

## What the existing timer measured

The signed lookahead producer starts its thread CPU clock before path parsing and stops it after descriptor cleanup. Inside that envelope it pins the recording directory, opens the member without following links, checks descriptor identity, obtains one private bounded `np.empty` destination, fills it using `readv`, checks EOF and rechecks identity. Time scheduled in the kernel on the producer's behalf counts in that timer. Time asleep waiting for I/O or CPU scheduling does not count. The timestamp excludes the consumer's final path identity check, complete compressed SHA, decode and verification. `demand_wait_ns` is consumer wall time waiting for a future, which can overlap worker work. The producer shares CPU2 with the consumer, and acquisition process CPU already includes worker CPU. Those two reported costs cannot be added together.

The signed fused per-member `complete_encoded_auth` and neighboring phase clocks use **process** CPU and input-block accounting. They cover a particular main-thread boundary and can include concurrent worker activity. On DS30-0178, all 14 segment-start envelopes crossed a process input-block increment, as did 11 of 92 envelopes for prefetched members. The total of those 106 recorded increments is 2,508,320, versus 16,642,192 across the child. The old envelopes do not identify which thread or system call was charged. Worker `readv` user/system, faults, block counts and open time were absent from frozen campaign receipts. [Pinned prefetch implementation](../../../tools/pipeline_eval/variants/experimental/receiver_member_prefetch.py) · [Pinned descriptor](../../../tools/pipeline_eval/variants/experimental/receiver_ingress.py) · [Fused read boundary](legacy_fused_map.py) · [Process clock](legacy_block_seek.py)

| Original and boundary | Authenticated acquisition wall / CPU, s | Lookahead hits / decimal GB | Worker CPU, s | CPU s/GB | Consumer wait, s | Child input blocks |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DS30-0178 frozen pair | 40.573 / 36.882 | 92 / 7.221 | 11.039 | 1.529 | 2.607 | 16,642,192 |
| DS30-0049 frozen ordered pair | 6.046 / 5.592 | 14 / 1.046 | 1.621 | 1.550 | 0.246 | 1,268,688 |
| DS30-0049 earlier successor attempt, same bytes | 6.521 / 6.055 | 14 / 1.046 | 2.253 | 2.154 | 0.511 | 2,544,576 |
| DS30-0107 frozen pair | 0.124 / 0.124 | 0 / 0 | 0 | — | 0 | 280 |
| DS30-0016 earlier resident original | 3.015 / 3.014 | 11 / 0.835 | 0.169 | 0.203 | 0.000065 | — |

The earlier DS30-0049 child belongs to a recovered generation for which the paired evaluator did not issue a verified pair. Its producer receipt matches the later verified native digest, raw authority, hit count and exact bytes. The 0.632 s variation in its worker CPU is real despite that unchanged input. DS30-0107 has one member and pays no lookahead work. The 0016 archive also includes earlier paid resident worker times of 0.165, 0.175 and 0.627 s over the same bytes with full lookahead. These runs demonstrate a variable cost which the frozen aggregate cannot locate. [Earlier resident comparison](resident-original-demand.md) · [Earlier synchronous snapshot](legacy-snapshot-reuse.md)

## Direct measurement on the complete resident 0016 original

Four fresh detector-hook children used the exact normal acquisition, 20/8 receiver and held-anchor selection. A narrow observer wraps only the original worker descriptor's `np.empty`, `readv`, descriptor `fstat` and EOF `read` via a source-pinned isolated namespace. The remaining original worker envelope includes top-level path/open/check/cleanup, Python and observer overhead. Thread CPU uses `thread_time_ns` and `RUSAGE_THREAD` supplies user/system, fault and block counts. The separately sampled counters can differ slightly from the narrow syscall timer. The observer and all signed checks ran in both arms.

The two-slot arm changes only destination allocation for actual lookahead calls and preserves ordinary reads at demand. Both slots use a leased NumPy owner retained by readonly memoryviews and NumPy `frombuffer`, including the actual decoder. The worker cannot reuse a live slot. Busy, closed or excessive allocations use ordinary private storage. The bounded retention is at most two 128 MiB slots and peaked at **157,459,225 bytes** in this trial. Each candidate allocated four times while the two slots grew and reused seven destinations. Every use read fresh original bytes. Consumers retained their existing identity validation, original index and encoded hashes, frame validation and every decoded visit digest. [Lifetime and ABI tests](../../../tests/pipeline_eval/test_prefetch_snapshot_accounting.py)

| Paid boundary | Fresh 1 | Reuse 1 | Reuse 2 | Fresh 2 |
| --- | ---: | ---: | ---: | ---: |
| Worker CPU, s | 1.658 | 0.651 | 0.598 | 1.395 |
| Worker `readv` CPU / system CPU, s | 1.654 / 1.652 | 0.641 / 0.640 | 0.591 / 0.590 | 1.392 / 1.392 |
| Allocation-call CPU, ms | 0.662 | 6.990 | 3.827 | 0.268 |
| Descriptor `fstat` / EOF `read` CPU, ms | 0.187 / 0.033 | 0.099 / 0.040 | 0.094 / 0.031 | 0.075 / 0.032 |
| Remaining worker CPU, ms | 3.394 | 3.314 | 3.347 | 3.345 |
| Worker `readv` minor faults | 168,033 | 75,798 | 49,737 | 121,532 |
| Consumer wait, ms | 165.592 | 0.064 | 0.064 | 13.673 |
| Inner acquisition wall / CPU, s | 5.083 / 5.081 | 3.706 / 3.700 | 3.720 / 3.720 | 4.347 / 4.343 |
| Launch through detector commit, s | 5.536 | 4.113 | 4.110 | 4.735 |
| Exit wall / CPU, s | 5.597 / 5.538 | 4.170 / 4.149 | 4.163 / 4.161 | 4.790 / 4.785 |
| Exit system CPU, s | 2.344 | 0.976 | 0.939 | 1.591 |

All 242,675 pages of the 28 original enrolled source files were resident before and after each child. The source was a private read-only bind over the enrolled tmpfs, and ordinary and lookahead member scopes charged zero input blocks. One fresh child's full process still reported 14,472 input blocks and 29 major faults elsewhere. Each measured worker performed eleven `readv` calls and supplied eleven hits covering the same 834,805,982 bytes, with zero fallbacks and zero major faults or input blocks. Each child reproduced native SHA-256 `aeb4658b886daaa4f8a93e99224fb4471f032f91feaa5ce58be2361d7009b4ac` and the same unfiltered selection. No terminal, fit, grid or plots were produced.

The fresh worker charged **1.67–1.99 CPU s/GB** on resident pages, exceeding DS30-0178's 1.53. Memory allocation calls themselves took under 1 ms. The CPU and fault reduction following the only intervention, destination reuse, places the removable cost in the kernel `readv` path associated with cold destination pages. The experiment does not break down individual kernel work such as copy, physical page allocation, accounting and zeroing. It also cannot apportion the archived long-run worker CPU, because those worker syscalls were never measured separately.

## DS30-0178 remaining cost

The verified original pair was **94.459 → 56.951 s** at the cohort's raw launcher plus common verification boundary. This is **9.722 s** above half the installed time. Native receiver calls were **18.093 wall / 16.694 CPU s** within the 40.573 s acquisition. Eliminating all 2.607 s of recorded consumer wait at that boundary would still leave 7.115 s. The successful 0016 lease reduction is **0.797–1.007 worker CPU s per eleven** hits. A sensitivity calculation applying it per member to 92 hits gives **6.67–8.42 worker CPU s**. If that saving transfers and every removed CPU second translates to elapsed time at the same boundary, **1.30–3.05 s** of the 0178 gap would remain. This is a pricing model. It neither prices cold source I/O nor turns signed receipts into a measured 0178 speedup. The combination merits a matched complete raw validation outside the frozen campaign.

The frozen resident launch and probe are at `410fbc527`. The sealed resident result SHA-256 is `e395cfb23e155b13373e77bda89262be84605f22869922a17e82d79f020a8af9`. The 28 focused and adjacent tests passed. A bounded lock attempt exited without source access during the campaign. The four measured children used a later naturally free lock and a single CPU2/nice15/ionice7 lease. No backup warming or full-campaign code was changed.
