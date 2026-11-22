# Small reusable Zstandard windows in full-scan ALGO08v2

Reusing just the Zstandard context saved a median **0.82 ms of verified-reader CPU** on DS30-0016 and cost **0.52 ms** on the northern simulation. Adding two reusable output buffers cost a median **2.42 ms** and **0.75 ms**, respectively. The full-scan candidate retains its current streaming reader. [Exact timings and freeze pins](measurements/zstd-window-acquisition.json)

| Saved source and scope | Mean acquisition CPU, released stream / persistent context / readinto | Mean verified-reader CPU, released stream / persistent context / readinto |
|---|---:|---:|
| DS30-0016 physical, 128 scheduled and 116 admitted | 0.934 / 0.928 / 0.937 s | 0.265 / 0.264 / 0.268 s |
| Northern public simulation, 128 scheduled and admitted | 0.929 / 0.973 / 0.945 s | 0.290 / 0.332 / 0.315 s |

The physical acquisition CPU differences by matched repeat ranged from 13 ms slower to 22 ms faster with a persistent context, and 30 ms slower to 16 ms faster with `readinto`. Several northern arms incurred sharply higher minor page-fault counts alongside higher reader CPU. The table retains every repeat. The paired reader medians give the clearer view of a sub-millisecond persistent-context effect on these inputs. Each `readinto` run allocated two buffers, reused them 126 times and loaned all 128 windows. All 36 timed acquisitions reproduced the raw authority, ordered factors and full detection document digest within their source. The timing excludes localization and publication.

## Scope

The earlier `readinto` trial eliminated owned-window allocations and measured 75–76 ms of decompression per 64-window chunk versus 74–78 ms for the released stream. Both paths still used Zstandard's streaming output and history buffers. The earlier whole-member direct decode avoided part of that cost by writing an entire member at once. Its two live output arenas needed 204.8 MB. This experiment isolates reuse of the streaming context and reuse of the per-window output buffers on the current full two-scan candidate. [Earlier readinto trial](receiver-decoded-ingress.md) · [Whole-member acquisition trial](zstd-conditional-acquisition.md)

All modes use the same compressed-member reader, paired window and chunk SHA-256 checks and approved `dd2d83a8` all-scan receiver. The candidate modes keep one Zstandard decompressor across both chunks. `readinto` additionally lends up to two 1.6 MB buffers. Each NumPy export retains a read-only loan until every derived view is released. An overlapping iterator gets its own canonical stream, and exhausted loans fall back to the stream's owned bytes. Both modes leave malformed-frame behavior to the same Python Zstandard backend. The 87 targeted tests include matching full and clipped scope errors against the released iterator, loan lifetime and overlapping reads. [Experimental shim](../../../tools/pipeline_eval/variants/experimental/receiver_window_ingress.py) · [Component tests](../../../tests/pipeline_eval/test_experimental_receiver_arena_ingress.py)

## Reproduction

The experiment was frozen at commit `f269dc4d0` by overlaying its recorded trial files onto a digest-checked copy of `integration-full-float-phase-signed/tools`. Keep the reviewed publication bundle as the binary and specification source. The timed interval begins before reader and detector setup and ends after producing the complete prefix's detections. A control preload warms the files and shared libraries. Alternate and rotate the three modes over six repeats on each source. Use the recorded manifest digests for the same two complete chunks of each recording.

```sh
bench=/tmp/leo-algo08v2-2x-bench
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
base="$bench/integration-full-float-phase-signed"
frozen="$bench/full-window-f269dc4d0"
flock "$bench/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
  env PYTHONPATH="$frozen:$release/src:$release" OPENBLAS_NUM_THREADS=1 \
  OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 "$release/venv/bin/python" -BPs \
  -m reports.ALGO08.single-core-2x.zstd_window_acquisition_trial \
  "$recording" "$manifest_digest" "$release/assets" "$base/spec.json" \
  c8d1020e20b29c2c98359d74d72f3c799a66c22bff4ac5230a727213c5639546 --repeats 6
```

For the physical source insert `sudo -n -u leo --` before `env`.
