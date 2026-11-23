# Exact verification of wholly unpaid compressed members

Skipping native receiver work on two complete DS30-0008 members still required **247–248 ms CPU and 269–307 ms elapsed** for verified input and empty-probe emission. The native drain saved **24–25 ms CPU** versus the released reader on that tail, about **9%**. Both paths kept all original input checks and reproduced the same 384 ordered probes, 19 retained selections, delivery clocks and raw authority. [Frozen comparison](native-verified-drain-protocol.md) · [Measured receipt](measurements/native-verified-drain.json)

## What compression and the authenticated fields prove

Each of the two unpaid members contains 64 stereo windows and 102,400,000 decoded bytes. The native frame reader found one ordinary Zstandard frame spanning each entire compressed member. Its decoding history window was 512 KiB, maximum block size 128 KiB, and frame header six bytes including magic. Each frame omitted the optional decoded-size field and carried the Zstandard content checksum. There was no sequence of independently compressed windows or seek table. Ordinary blocks may depend on earlier block contents and entropy state. The seekable extension instead stores separately compressed frames and a seek table in a skippable frame. Zstandard’s optional content checksum truncates an xxHash of the decoded contents to 32 bits. [Zstandard frame specification](https://github.com/meta/zstd/blob/v1.5.7/doc/zstd_compression_format.md) · [Seekable format specification](https://github.com/meta/zstd/blob/v1.5.7/contrib/seekable_format/zstd_seekable_compression_format.md)

The compressed SHA-256 identifies the compressed byte stream. The index digest identifies the bytes declaring window sizes and decoded SHA-256 values. The bound manifest also identifies the separately declared SHA-256 of the decoded member. Field authentication cannot establish equality between the decoded stream and these declarations. In one test, fresh authenticated index bytes contain a wrong window digest while the compressed member and full decoded member digest are correct. In a second, all the window digests and compressed bytes are correct while the newly bound manifest carries a wrong full decoded digest. The released and native readers reject both before accepting the scope. Neither construction requires a SHA collision. [Independent inconsistency tests](../../../tests/pipeline_eval/test_native_verified_drain.py)

The standard whole-member digest is SHA-256 of the concatenated decoded bytes. The finalized per-window digests include each individual window's padding, so those digest values do not supply the SHA-256 chaining state for the full member. A prior trusted statement that binds the exact compressed bytes, decoder and decoded checks could supply another basis for reuse. The current approval boundary performs the decoded checks in the current traversal. Even a seek table would only improve access to compressed subranges while the requirement to verify every decoded byte remains.

## Paired cold measurements

Both arms use the original first three DS30-0008 members on a fresh private XFS copy. The scope contains 192 scheduled and admitted visits. The first 64 receive the installed signed two-scan detector and continuation. For the next 128, both arms emit empty metadata rows which still advance continuation. The original compressed reader and paired SHA-NI implementation are pinned. Both use serial demand reads so the measurement isolates the drain and its cold input duty. The previous prefetch experiment remains a separate comparison. [Cold prefetch and released advice](sparse-cold-input.md)

The native drain authenticates the compressed bytes and index with the original storage port, then streams libzstd output through one reusable 1.6 MB application buffer. The existing paired SHA code verifies each decoded window and updates the full member hash in the same pass. No tail CI16 array or persistent decoded output is constructed. The native code checks exact input consumption, frame completion, decoded extent and both digest levels before exposing original metadata. Other recognized frame layouts fall through to the released decoder. Decoder state and the compressed input buffer still use memory. [Native streaming checker](native_verified_drain.c)

| Bound and order | Released CPU | Native CPU | Released elapsed | Native elapsed |
|---|---:|---:|---:|---:|
| Two unpaid members, released first | 273.79 ms | 248.43 ms | 322.30 ms | 307.26 ms |
| Two unpaid members, native first | 271.13 ms | 246.81 ms | 292.66 ms | 269.20 ms |
| Full 192 visits, released first | 787.08 ms | 754.40 ms | 863.35 ms | 813.32 ms |
| Full 192 visits, native first | 858.11 ms | 746.51 ms | 879.73 ms | 768.96 ms |

The tail clock begins after the 64th admitted visit and includes closing the first member's reader, both unpaid member traversals and the empty callbacks. Native tail cost includes **112.3–112.8 ms** decode and frame checks, **46.7–46.8 ms** paired decoded SHA, **83.0–84.0 ms** compressed reads and SHA, and 1.9 ms of index checks. Remaining clock time covers call, iterator and metadata work. This is an observed serial floor on this fixture. The complete acquisition clocks vary more than the isolated tail savings. That variation limits attribution of the complete difference to the drain.

All four arms started with zero observed file pages in the three private compressed payloads. Three arms were charged **453,304** input blocks, or **232,091,648** page-rounded bytes. The first released run charged 96 additional blocks. The logical payload is **232,083,693 compressed bytes** per acquisition, including **154,640,914 bytes** across the unpaid members. There was no native fallback. Empty file pages establish the measured Linux cache state. Lower storage caches and staging extent effects remain outside the observation. The retained factors were checked against the sealed installed v3 archive. No position solve or full-recording timing was performed.

## Reproduction

The benchmark used commit `9b4581b69`. The measured native binary SHA-256 was `2de0e51b5f5acbe53d12f011cb72d919a9b77be60ec32dddfb9aff7f5397e8bc`. A follow-up puts the exact single-frame extent check ahead of the optional advertised content size. This preserves the canonical handoff for concatenated frames whose first advertised size describes only part of the member. The two measured single-frame inputs lacked an advertised content size, so the change only affects an unmeasured fallback case. Both advertised and unknown-size concatenated layouts are covered by the focused tests.

Run from the experiment worktree on Gauss, with a fresh build and receipt path. Two reversed cold pairs stay inside one Gauss lock, CPU 2, nice 15, best-effort I/O level 7 and one numerical thread. The script stages only private copies and removes them on exit. Use the measured revision to reproduce the original native binary.

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
lock "$release/venv/bin/python" -BPs -m reports.ALGO08.v3.native_verified_drain "$new_work" \
  > "$new_receipt"
lock "$tree/.venv/bin/python" -BPs -m pytest -q tests/pipeline_eval/test_native_verified_drain.py \
  tests/pipeline_eval/test_first_third_ingress.py tests/pipeline_eval/test_sparse_cold_input.py
```
