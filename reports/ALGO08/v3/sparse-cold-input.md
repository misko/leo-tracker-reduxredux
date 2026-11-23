# Cold prefetch with one-third detector duty

Reading one whole signed member ahead saved **113.76 ms** in the cold pair that ran v3 advice first. In the reversed pair, prefetch was **1.72 ms slower**. Every arm charged the same **232.092 MB** of filesystem input and reproduced all 384 ordered probes and 19 selected observations. The first-arm difference dominates this private XFS test and the reversed pair does not reproduce the large gain. [Frozen protocol](sparse-cold-input-protocol.md) · [Timing, I/O and signed-input receipt](measurements/sparse-cold-input.json)

## Matched cold arms

The test copied the original signed manifest and the first three compressed members and indexes from DS30-0008 into a private XFS directory. The members contain **232,083,693 compressed bytes**, **307,200,000 decoded bytes** and 192 stereo visits, all admitted. The timed index prepass identified the first admitted third and paid for 64 complete native v3 stereo callbacks. On the remaining 128 visits, empty probe rows advanced the same lane histories. Both paths still decoded and hashed every original window and authenticated each index, compressed member and complete decoded member. They validated the original delivery clocks.

The advisory arm uses the pinned v3 one-buffer input and paired decoded SHA-256 plus its two 16 MiB hints. The async arm replaces the hints with the existing single-worker full-member reader. It supplied both following members on each async execution, totaling **154.641 MB**, with zero fallback. It spent **50.1–51.5 ms** of worker CPU included in the measured process clocks. Total collection wait was **9.2–14.5 µs**. The read buffers went through the same compressed digest verification at demand. The timer covers the authenticated index plan, input, both signed scans on each paid visit, continuation and construction of the acquisition document. [Existing prefetch implementation](../../../tools/pipeline_eval/variants/experimental/receiver_member_prefetch.py)

| Pair and execution order | Mode | Wall s | Process CPU s | Paid callback CPU s | Compressed throughput, MB/s |
|---|---|---:|---:|---:|---:|
| 1 first | v3 advice | 0.88343 | 0.78764 | 0.35309 | 262.7 |
| 1 second | Async whole member | 0.76967 | 0.76956 | 0.34782 | 301.5 |
| 2 first | Async whole member | 0.76868 | 0.76862 | 0.34976 | 301.9 |
| 2 second | v3 advice | 0.76696 | 0.76260 | 0.33971 | 302.6 |

Throughput divides original compressed bytes by the acquisition wall clock. All arms started with **zero** observed pages across the three compressed files. All ended with the same 56,663 pages resident and charged **453,304** 512-byte input blocks in process resource accounting. The all-thread `/proc/self/io` measurement independently records **232,091,648 bytes** read per arm, the page-rounded size of the three original members. The test processed **928.335 MB** of compressed data across four timed acquisitions. Creating the private fixture read another **232.084 MB** of original compressed bytes once.

## What the reversal shows

The first advice arm used 95.79 ms more wall than process CPU. That gap was only 4.35 ms on its second execution. The two async gaps were each below 0.11 ms. The process ran all arms serially on one core, so these gaps report elapsed time outside charged process CPU. They cannot isolate disk service from scheduling or start-up. First-arm module and detector initialization, lower RAID cache state, and the privately staged extents were not reset between arms. Only the common Linux compressed-file page state and input-byte charges were matched. The async worker completed both speculative reads before demand under sparse DSP. The measured timings do not establish a repeatable elapsed gain over advice.

The prior generated 192-window XFS fixture ran full DSP and reported **149 and 299 ms** of incremental gain with two reversed cold orders. The recent first-third drain comparison used real saved members but charged zero input blocks. The current pair adds real saved compressed input at sparse duty and covers one private extent layout. [Generated full-DSP cold comparison](../single-core-2x/full-member-prefetch.md) · [Warm first-third ingress comparison](first-third-ingress.md)

## Reproduce

The scope binds the installed detector, runtime reader, original 512-window manifest, archived native probes and the cache observer. The copy includes only its first 192 windows. Cache advice checks the independently created owner-private inodes before applying file-specific eviction. Compressed copy bytes are bounded and authenticated before use. The temporary copy is removed at exit. Thirty-one focused tests passed, including tampered staging bytes, bounds, hard-link rejection, probe masking and the existing decode and prefetch integrity cases. [Runner](sparse_cold_input.py) · [Component tests](../../../tests/pipeline_eval/test_sparse_cold_input.py)

```bash
bench=/tmp/leo-algo08v2-2x-bench
tree=/home/mouse9911/gits/leo-tracker-reduxredux
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
lock() {
  flock -x "$bench/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 timeout --signal=INT 55s \
    env OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="$PWD/reports/ALGO08/v3:$PWD:$release/src:$release" "$@"
}
lock "$release/venv/bin/python" -BPs -m reports.ALGO08.v3.sparse_cold_input /srv/bulk/leo-dev \
  > "$new_receipt"
lock "$tree/.venv/bin/python" -BPs -m pytest -q tests/pipeline_eval/test_sparse_cold_input.py \
  tests/pipeline_eval/test_first_third_ingress.py \
  tests/pipeline_eval/test_experimental_receiver_member_lookahead.py
```
