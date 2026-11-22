# Reusable Zstandard output for verified receiver ingress

Decoding into a reused 102.4 MB destination saved **14–16 ms of decompression CPU per 64-window chunk**. Exact window and chunk verification left **12–14 ms** of savings. The deferred receiver then spent **23–24 ms** making immutable snapshots of the borrowed windows, putting the measured stages together at **8.5–12.2 ms slower per chunk**. The prototype stays at the decode benchmark boundary. [Per-chunk timings and hashes](measurements/zstd-arena.json)

| Two sealed chunks per source | DS30-0016 physical | Northern public simulation |
|---|---:|---:|
| Warm decompression, existing stream | 72.04 ms | 72.15 ms |
| Warm decompression, direct reusable destination | 55.66 ms | 58.19 ms |
| Warm decompression, stable-output stream | 57.53 ms | 59.65 ms |
| Window and chunk SHA-256, existing stream → direct | 40.83 → 43.11 ms | 40.65 → 42.85 ms |
| Deferred snapshot, owned → borrowed window | 0.20 → 22.82 ms | 0.17 → 24.10 ms |
| Sum of measured stages, existing stream → direct | 113.06 → 121.58 ms | 112.98 → 125.13 ms |

The warm timing alternated the two chunks and rotated the three modes over five repeats. The snapshot measurement took separate timings for the existing `_immutable_iq` call. It held up to 32 recent snapshots and applied the production window-admission check, which admitted 58 physical and 64 simulated windows per chunk. The reader's bytes-backed arrays bypass that copy. A read-only view of the arena requires a copy for the current deferred consumer. The two estimates use process CPU and include both SHA-256 checks. [Harness](zstd_arena_trial.py)

First direct decode, including destination page faults, took 63.8 ms physical and 66.4 ms simulated, versus 74.4 and 73.8 ms for the first existing stream. The second chunk reused the same destination and took 55.6 and 58.3 ms. Context creation and virtual allocation took under 0.1 ms. Touching the destination's pages in advance took 10.1–10.2 ms. Dedicated warm-up decodes were excluded from the repeated timings. The optimistic arithmetic before snapshots and ownership would remove approximately 0.18 CPU seconds on the 808-window physical recording and 0.22 seconds on a 1,200-window simulated recording. Scaling the physical per-chunk result to the 6,770-window recording would suggest about 1.5 seconds under the same decode and hash conditions.

## Frame extent and buffer lifetime

The harness verified the compressed and index member sizes and SHA-256 before timing. Every arm checked index geometry, all 64 window SHA-256 digests and each full decoded chunk digest. The four existing frames omit a content-size field. The prototype accepts an unknown or matching declared content size, bounds the destination to 128 MiB, checks that the first frame consumes the entire member, and requires exactly the expected output length. The stable-output operation also checks that both input and output cursors end at the sealed bounds. The tests cover truncation, checksum failure, size mismatches, extra bytes, a second frame including an empty one, reuse after failure and the existing deferred snapshot behavior. The canonical reader remains responsible for unsupported frames and their existing error or success behavior. [Native calls and guards](../../../tools/pipeline_eval/variants/experimental/receiver_zstd_arena.py) · [Component tests](../../../tests/pipeline_eval/test_experimental_receiver_zstd_arena.py)

The benchmark finishes consuming each destination before reuse. A public reader call yields views that can outlive it, and the current iterator holds the previous window while moving to the next chunk. Reusing a single buffer at that boundary would overwrite a live view. A two-buffer scheme would need about 204.8 MB for these chunks and would still require the streaming path when both buffers are borrowed. An explicit ownership mechanism would also have to preserve the current order of window validation and the protection afforded by the immutable deferred snapshots.

## Reproduction

The four chunks are the first two complete members from each source listed in the receipt. The benchmark used Python `zstandard` 0.25.0 with bundled Zstandard 1.5.7 for the stream control and system libzstd `1.5.7+dfsg-3` for both native modes. The receipt records the system library digest and the Python backend extension digest. Use `sudo -n -u leo --` immediately before `env` for the physical source. [Saved sources and library pins](measurements/zstd-arena.json)

```sh
bench=/tmp/leo-algo08v2-2x-bench
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
flock "$bench/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
  env PYTHONPATH="$PWD:$PWD/src:$release" OPENBLAS_NUM_THREADS=1 \
  OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 "$release/venv/bin/python" -BPs \
  -m reports.ALGO08.single-core-2x.zstd_arena_trial "$recording" \
  --library /usr/lib/x86_64-linux-gnu/libzstd.so.1 \
  --library-sha256 060eeb79531d435306665fd78329d8a9dd579f95876c5960bb67937825362a80
```
