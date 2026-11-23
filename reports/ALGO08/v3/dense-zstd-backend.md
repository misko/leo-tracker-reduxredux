# System libzstd decodes the signed dense member faster

The distro Zstandard 1.5.7 build reduced the installed binding's measured streaming read CPU by **13.2% and 13.7%** on one authenticated 64-visit member of DS30-0008. Calling both builds through the same stream bridge preserved the improvement. Total acquisition CPU moved **+1.64 ms** and **−9.09 ms** in the two reversed orders. The frozen rule requires an improvement in complete acquisition in both orders before advancing the decoder. [Frozen protocol](dense-zstd-backend-protocol.md) · [Full timings and authority receipt](measurements/dense-zstd-backend.json.gz)

## Matched reads with one owned output per window

All arms used the same reader, full-short receiver schedule and original integrity checks on **77,442,779 compressed bytes**, **172,750 index bytes** and **102,400,000 decoded bytes**. Each executed the 64 normal window reads and final trailing-byte read, 16 full and 112 short native receiver calls, and every SHA-256 check. Every arm started and ended with all **18,907** compressed pages resident. The stock binding and both bridge paths returned one owned Python `bytes` value per window. The bridge passed the whole authenticated compressed snapshot to the native decoder and charged one frame-layout check in acquisition. It used exactly 64 native decode calls per member. Both bridge builds decoded the whole member without falling back.

| Order | Decoder | Zstandard read CPU ms | Acquisition CPU ms | Acquisition elapsed ms | Acquisition outside native receiver CPU ms |
|---|---|---:|---:|---:|---:|
| 1, first | Installed Python c extension | 70.919 | 295.317 | 296.339 | 134.777 |
| 1, second | Bundled libzstd through bridge | 71.033 | 294.383 | 294.549 | 134.595 |
| 1, third | System libzstd through bridge | 61.556 | 296.956 | 297.114 | 128.484 |
| 2, first | System libzstd through bridge | 61.802 | 291.073 | 291.225 | 126.474 |
| 2, second | Bundled libzstd through bridge | 72.345 | 301.839 | 302.011 | 137.677 |
| 2, third | Installed Python c extension | 71.636 | 300.159 | 300.295 | 136.198 |

The matched bridge isolated **9.48 and 10.54 ms** of read CPU per member, **13.3–14.6%**. Time inside its libzstd calls fell from **70.49 to 60.83 ms** and from **71.68 to 61.18 ms**. The complete acquisition outside native receiver calls improved by **6.29 and 9.72 ms** against the installed binding. The first system arm also had **7.93 ms** more CPU in native signal detection, despite the same detections and schedule. These scopes exclude the immutable seal, which added between 1.22 and 5.70 seconds elapsed across arms on the private filesystem. Resident payload scans charged **0–120 input blocks**. The fixture was staged once in **13.120 s** outside the timed arms. [Prototype](dense_zstd_backend.py) · [Timing entry](dense_zstd_backend_trial.py)

## Distinct builds and integrity

The installed `zstandard` 0.25.0 c extension contains its own Zstandard 1.5.7 and does not dynamically link libzstd. Its symbol table has the C implementations of the BMI2 Huffman decoder functions. The local `libzstd1` and `libzstd-dev` packages are both 1.5.7+dfsg-3. The static distribution archive also contains the x86-64 assembly functions `HUF_decompress4X1_usingDTable_internal_fast_asm_loop` and `HUF_decompress4X2_usingDTable_internal_fast_asm_loop`. Comparing the 128 bytes after `endbr64` in its two routines locates their signatures at `0xb2c84` and `0xb3101` in the loaded shared library. Neither appears in the installed extension. Both also appear in the already installed Pillow libzstd 1.5.7. The distro library was the only external measured arm. Function-level execution was unmeasured, so the read improvement belongs to the system build as a whole.

The research bridge uses the pinned ELF symbol offsets to locate the private bundled functions for the apples-to-apples control. The system arm calls public libzstd symbols. The bridge activates only for one complete standard frame. It uses the original Python reader for other layouts and replays the original reads after a bridge-reported decoding error. The stock reader still authenticates the manifest, compressed and index digests, every decoded window, and the complete decoded member. The six complete sealed detector files have the same SHA-256 `856affd89c8d3effd46c766efd9d02919c14641ad6b9837f3dc685f9f757ba2e` and 67 identical signed candidates. All 64 per-window digests match the earlier independently pinned prefix. Tests cover incomplete and concatenated frames, trailing input and corrupt checksums, and independently inconsistent compressed, index, decoded-window and decoded-member authorities. **25 component and adjacent tests passed.** [Tests](../../../tests/pipeline_eval/test_dense_zstd_backend.py) · [Previous ingress attribution](dense-ingress-attribution.md)

## Dense cost envelope

Repeating the **9.36–9.83 ms** local streaming read gain at the same rate across all 6,772 issued visits would save **0.99–1.04 CPU s**. The whole raw candidate is **12.800 CPU s** above half of the historical same-recording stock CPU. Even the earlier estimated **7.514 CPU s** for its entire Zstandard read stage, if removed at zero cost, would leave the candidate above that target with other CPU fixed. The standard reader's original compressed and decoded hashes remain mandatory. These are single-member estimates under comparable per-visit byte rates, with no cold-input or whole-recording runtime measurement for the system decoder. [Dense raw clocks](dense-full-short-raw.md) · [Prior buffer-layout experiment](../single-core-2x/zstd-arena.md)

## Reproduce

```bash
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
short=/var/tmp/leo-mixed-aperture.pdUjDb1S/build-v2/short-primary.so
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2 \
  env PYTHONPATH="$PWD:$PWD/src:$release/src:$release" PYTHONDONTWRITEBYTECODE=1 \
  OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  timeout 90s "$release/venv/bin/python" -BPs -m reports.ALGO08.v3.dense_zstd_backend_trial \
  run /srv/bulk/leo-dev "$short" "$fresh_output"
```
