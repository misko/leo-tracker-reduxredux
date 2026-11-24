# Synchronous demand reads on a verified resident original recording

Keep ordinary next-member lookahead. On the single matched complete DS30-0016 pair, synchronous demand reads increased launch-to-detector elapsed from **3.358 to 3.675 s** and inner acquisition CPU from **2.941 to 3.249 s**. Both emitted exactly the earlier standard detector file. The extra work is concentrated in authenticated encoded reads and their faults. A separate exact decoded-window lease removed faults in the four-member pilot with small and order-dependent acquisition timing. [Frozen demand protocol](resident-original-demand-protocol.md) · [Full timing and source evidence](measurements/resident-original-demand-0016.json.gz) · [Decoded lease pilot](owned-window-recycle.md)

## Complete matched scope

Two fresh children used the same pinned installed runtime and 20/8 detector with two-scan 20 ms anchors, normal no-map direct-to-owned verification, complete original inventory and held-history selector. Both began at the standard raw entry and used the same detector-only hook before the graph/solver/renderer path. The control used ordinary next-member lookahead. The demand child disabled its wrapper only after verifying the enrolled read-only mount and full residency. On an unqualified source the experimental selector keeps ordinary lookahead. Each demand member still pays the ordinary descriptor read into a private snapshot, complete encoded SHA, exact frame and checksum verification, original index/decoded-member SHA and individual window digests. The same snapshot after read is used by the decoder.

All **242,675 pages** of the 28 enrolled original files were resident before and after both children. Neither the encoded verification scopes nor the lookahead worker charged a process input block. The lookahead child recorded one major fault and 32 input blocks elsewhere in its whole-process clock. All **991,734,597 compressed bytes** and **808 signed visits**, including 95 exclusions, were covered in both arms. Each used the original ordered member/index/decoded commitments and unfiltered selection and produced the same **1,426 probes and 506 factors** as the previously published detector file at SHA-256 `aeb4658b886daaa4f8a93e99224fb4471f032f91feaa5ce58be2361d7009b4ac`.

| Paid stage | Normal lookahead | Synchronous demand |
| --- | ---: | ---: |
| Launch to outer acquisition, s | 0.335536 | 0.351828 |
| Inner acquisition elapsed / CPU, s | 2.962292 / 2.940972 | 3.262541 / 3.248870 |
| Held selector elapsed, s | 0.051821 | 0.052383 |
| Launch through detector commit, s | 3.357700 | 3.674879 |
| Exit elapsed / CPU, s | 3.415047 / 3.389574 | 3.724556 / 3.705674 |
| Process user / system CPU, s | 3.140313 / 0.249261 | 3.206770 / 0.498904 |
| Process minor faults | 29,759 | 95,642 |
| Worker-supplied snapshots / bytes | 11 / 834,805,982 | 0 / 0 |
| Paid demand snapshots / bytes | 2 / 156,928,615 | 13 / 991,734,597 |
| Main-thread encoded read and SHA CPU, ms | 237.347 | 637.788 |
| Speculative worker read CPU, ms | 164.705 | 0 |
| Both encoded-read scopes, user / system CPU, ms | 209.335 / 192.717 | 216.053 / 421.735 |
| Minor faults in the two encoded-read scopes | 6,055 | 71,974 |
| Minor faults at decoded output | 2,073 | 2,080 |

The ordinary worker's original internal clock was **164.608 ms CPU**, with 11 exact hits, zero fallback and **0.065 ms** cumulative demand wait. The thread-scope observer's read count adds wrapper timing, giving **164.705 ms**. Removing it shifted reads to the main thread and charged **235.736 ms** more total CPU for encoded read and authentication. The system part of those two read scopes increased **229.018 ms**, close to the increase of **249.643 ms** in whole-process system CPU. These scopes track descriptor reads as paid with the original authentication and do not isolate allocator faults from the kernel copy syscall.

The demand child incurred about 300–784 minor faults and 15–16 ms system CPU on most first-segment reads early in the run. Later demand reads incurred up to 15,565 faults and 101.842 ms system CPU in their encoded verification scope. Individual lookahead worker reads stayed at 214–778 faults and 9.883–16.124 ms system CPU. Both children used 18 logical decoded destination addresses, with 2,072–2,073 of their decoded faults in the first two members. No decoded allocator or science changes entered the pair.

## Interpreting the earlier variation

The 1→4 prefix benchmark put the reader on a subclass whose own fused windows method shadows the lookahead wrapper on the installed base class. Both fresh four-member stock controls confirmed zero speculative reads and paid complete demand copy and SHA. Ordinary full verify-once has a different method dispatch. The regression test exercises both. The new normal full hook reaches its detector in **3.358 s**, close to the old **3.372–3.392 s** two-point predictions by coincidence of paid totals across different routes. The new full demand child is the nearer scheduling comparison to those prefix runs and takes **3.675 s**. [Prefix dispatch evidence](owned-window-recycle.md)

The earlier archived normal full run charged **627.490 ms worker CPU** for the same 834.806 MB and 11 hits. The new control and the earlier mapped full run charged **164.608 and 174.640 ms** respectively. The gross old worker CPU therefore does not estimate removable work. The earlier **5.053 s** full-hook measurement also had more system CPU and faults. This matched pair localizes a large, variable cost to compressed destination and descriptor scopes under synchronous demand, while the decoded destination is already warm after the first few members. It leaves the exact trigger for the historical slow normal process unassigned. [Earlier full hook](original-full-detector-boundary.md) · [Earlier mapped encoded read](legacy-snapshot-reuse.md)

## Reproduce

Run `resident_original_demand.py launch FRESH_TMPFS_DIR` with the existing private original read-only bind, installed interpreter, shared CPU2 lock, nice 15, I/O priority 7 and one numerical thread. Run its `score FRESH_TMPFS_DIR` action after exit. The as-run commit was `8c802af37`. The uncompressed result SHA-256 is `201479c5c4f66c5f8f1fe6fb9521ddd69dc615d770b13d87f349194ed8283d17`. The 37 focused and adjacent tests passed. One original full pair, no backing waveform read, no solve, no deployment.
