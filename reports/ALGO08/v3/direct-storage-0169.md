# Original-storage mixed acquisition on DS30-0169 member 1

The unchanged mixed receiver verified one **78.62 MB** signed member directly from cold original storage at **112.09 MB/s**. The same member reached **89.90 MB/s** on the naturally resident repeat. Both fell below the conditional **207.46 MB/s** budget. The cold run needs **322.44 ms** removed from its **701.40 ms** acquisition clock. Its **420.36 ms** read alone exceeds the **378.97 ms** member allowance. [Frozen scope](direct-storage-0169-protocol.md) · [Clocks, input identities and factor receipt](measurements/direct-storage-0169.json.gz)

## Measured boundary

The experiment opened only original segment 0, member 1 and its manifest and index. It read the 78,620,639-byte compressed member once cold and once resident on XFS. Both workers used the frozen original compressed read, Zstandard stream decoder, and release paired SHA-256 for all 64 individual decoded windows and the complete 102,400,000 decoded bytes. Both verified the original manifest, index and compressed payload. Neither made a waveform copy, evicted pages, prefetched a future member, or read earlier waveform data. [Pinned driver](direct_storage_0169.py)

Member 1 begins at global visit 64. The 20/12 ms callback uses one full stereo anchor then seven short stereo primaries per actual RF stream. Each worker reconstructed the true starting counters independently from the earlier sealed member's 51 admitted stereo pairs and checked them against its saved schedule, along with the signed sample and clock boundary. This used only the existing verified metadata. The timed scope starts once the member-specific reader and receiver contexts are ready. The separate process clock includes fresh launch, imports, exact seed validation, setup, output and exit. [Earlier first-member receipt](measurements/receiver-ceiling-0169.json.gz)

| Stage | Cold wall / CPU, ms | Resident wall / CPU, ms |
|---|---:|---:|
| Index read, parse boundary and hash¹ | 0.43 / 0.27 | 0.20 / 0.20 |
| Compressed descriptor, all 78.62 MB | 420.36 / 26.02 | 594.66 / 594.36 |
| Compressed SHA-256 | 17.60 / 17.60 | 17.45 / 17.45 |
| Zstandard stream reads | 84.05 / 84.00 | 84.59 / 84.47 |
| Paired decoded window SHA-256 and final member digest | 23.83 / 23.83 | 23.97 / 23.93 |
| Paid native DSP | 147.37 / 147.24 | 144.01 / 143.97 |
| Remaining acquisition work¹ | 7.76 / 7.82 | 9.62 / 9.69 |
| **Verified acquisition total** | **701.40 / 306.77** | **874.51 / 874.07** |
| Fresh process launch through exit | 2720.05 / 2279.14 | 2879.56 / 2860.36 |

¹ The index row includes the complete index member lookup, read and hash. The separate released index model validation and other Python work are in the remainder. Separately metered syscall intervals sit within the compressed descriptor row and are excluded from the stage sum. The saved metadata seed itself took **1.19 ms wall** in each worker. Receiver context setup took **3.86 and 3.99 ms wall**. [Stage and resource counters](measurements/direct-storage-0169.json.gz)

The cold member began at **0 of 19,195 pages** resident and ended fully resident. The payload descriptor recorded **153,560 input blocks**. The resident repeat began and ended with all pages resident and issued **zero input blocks**. Its payload read syscalls accounted for **594.58 ms elapsed and 594.28 ms process CPU**, compared with **420.26 ms elapsed and 25.91 ms process CPU** cold. Other stages were similar across the two runs. This single pair locates the resident slowdown at the original read boundary. Its cause and repeatability remain unknown. [Read-only page observations and cross-run clocks](measurements/direct-storage-0169.json.gz)

## Wait budget and signed parity

At 207.46 MB/s, the cold member would need **322.44 ms**, or **81.8%** of the **394.34 ms** measured descriptor off-CPU interval, hidden or removed if all other measured work stayed fixed. The measured local work outside the descriptor supplied only **281.04 ms** to overlap, and the complete read would still cost at least **420.36 ms**, equivalent to **187.03 MB/s**, under same-member overlap. A counterfactual that removes all descriptor off-CPU time from this run yields **307.06 ms** or **256.04 MB/s**. That distinguishes the cold work budget from the observed serial elapsed rate. The resident repeat missed by **495.54 ms** and had only **0.30 ms** off CPU in the descriptor. Hiding storage waits alone cannot explain or recover the resident clock. No cross-member overlap or whole-recording rate was measured. [Budget arithmetic](direct_storage_0169.py) · [Conditional full-recording target](receiver-ceiling-0169.md)

Both workers admitted **56 of 64 stereo visits** and excluded eight. The seed placed seven full anchors and 49 short primaries, so each worker ran **14 full and 98 short lane calls**. Both produced the same **55 native factors**, including six rank 1, and the same **49 selected factors**, including one rank 1. All native tuple bytes and order, decoded-I/Q digests, visit metadata, exclusions and selected probe values matched. No position or frequency-fit comparison was run. [Ordered signed factors](measurements/direct-storage-0169.json.gz)

## Reproduction

The compressed receipt SHA-256 is `1cfa963cd4f0afdad16dfe8dc88e5003efa315f1cc4b763fda29850dd710c035`. It contains the exact benchmark JSON and the original verified prefix worker JSON. The benchmark read the staged metadata file. If that file is absent, the driver recovers the original pinned metadata bytes from the compressed receipt and performs the same checks. Thirteen tests cover the bounded member, admitted scheduling state, exact archived seed bytes, signed-factor comparison and disjoint timing arithmetic. Cache observation describes the actual initial state on a future reproduction. The command does not establish cold cache. [Component tests](../../../tests/pipeline_eval/test_direct_storage_0169.py)

```bash
install_root=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
gauss() {
  flock -w 60 -x /tmp/leo-algo08v2-2x-bench/gauss.lock \
    sudo -n -u leo ionice -c2 -n7 nice -n15 taskset -c 2 env \
    TMPDIR=/dev/shm PYTHONPATH="$install_root/src:$PWD:$PWD/src:$install_root" \
    OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 "$@"
}
gauss "$install_root/venv/bin/python" -BP -m reports.ALGO08.v3.direct_storage_0169 \
  run /dev/shm/leo-direct-storage-0169-rebuild
gauss "$install_root/venv/bin/python" -BP -m pytest -q -p no:cacheprovider \
  --basetemp=/dev/shm/leo-direct-storage-0169-rebuild-tests \
  tests/pipeline_eval/test_direct_storage_0169.py tests/pipeline_eval/test_receiver_ceiling_0169.py
```
