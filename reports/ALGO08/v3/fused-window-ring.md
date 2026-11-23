# Bounded Zstandard history returns verified owned windows

The bounded decoder reduced peak process RSS by **93.4–93.8 MiB** versus the full-member fused decoder on one authenticated DS30-0008 member. Its memory use matched the released reader within **0.7 MiB**. Complete acquisition CPU moved **+2.85 ms / −17.83 ms** against release in reversed orders, so the test establishes the memory saving while leaving the runtime effect uncertain. All six runs produced identical signed detections. [Frozen comparison](fused-window-ring-protocol.md) · [Complete receipt](measurements/fused-window-ring.json.gz)

## Bounded decoded history

The recorded frame advertises **524,288 bytes** of back-reference history and a maximum block of **131,072 bytes**. The system libzstd's `ZSTD_decodingBufferSize_min` returns **786,496 bytes** for that layout. The decoder uses that fixed ring in place of the previous **102,400,000-byte** member destination. It writes consecutive blocks until the next full block cannot fit, drains undelivered decoded bytes into the next consumer window, and then wraps. Both bounded runs exercised **130 wraps** and identical **1,567** input steps.

The decoder copies each completed sample byte once into its final owned Python bytes object. Those window objects remain immutable while the ring wraps or after its C context closes. The decoder's ring cap applies to frames advertising up to **8 MiB** history. Larger histories, unsupported frame layouts and dictionaries delegate to released owned-window delivery. The decoder never lends its mutable ring to the consumer. A consumer that retains many final windows keeps its own window allocations alive. The original full compressed snapshot and the decoder context are outside the ring size. [Bounded native decode](fused_window_ring.c) · [Owned-window binding](fused_window_ring.py) · [Original arena path](fused-block-input.md)

## Same signed member and receiver

All runs used one owner-private tmpfs copy of the same **77,442,779-byte** compressed member, manifest and index. All **18,907** compressed pages were resident before and after each fresh worker. Every worker charged zero filesystem input and output blocks. The prior full-member fused native binary reproduced its archived SHA-256 exactly. Both native modes use the same pinned system libzstd and installed paired SHA. The released control uses the installed bundled decoder. Each mode issued **16 full and 112 shortened native calls** and reproduced the same 64 decoded digests, manifest and index checks, and sealed detector output at `856affd89c8d3effd46c766efd9d02919c14641ad6b9837f3dc685f9f757ba2e`.

| Order | Ingress | Decode and output CPU ms | Paired SHA CPU ms | Acquisition CPU ms | Acquisition elapsed ms | Acquisition outside detector CPU ms | Peak RSS MiB |
|---|---|---:|---:|---:|---:|---:|---:|
| 1, first | Released | 70.509 | 23.580 | 295.140 | 295.284 | 137.084 | 328.1 |
| 1, second | Fused full-member arena | 62.963 | 23.518 | 295.640 | 295.791 | 130.877 | 422.2 |
| 1, third | Bounded ring | 61.851 | 23.415 | 297.990 | 298.155 | 130.614 | 328.8 |
| 2, first | Bounded ring | 60.428 | 23.304 | 288.219 | 288.340 | 127.422 | 328.7 |
| 2, second | Fused full-member arena | 63.200 | 24.386 | 305.731 | 305.894 | 133.085 | 422.5 |
| 2, third | Released | 72.543 | 23.772 | 306.053 | 306.232 | 140.395 | 328.8 |

The bounded decode clocks include copying all **102,400,000** bytes to the owned windows. Complete acquisition also charges frame inspection and allocation. Its CPU outside native detection fell **6.47–12.97 ms** versus release and **0.26–5.66 ms** versus the full arena. The native detector's own clocks changed enough to reverse the first pair's total CPU result. These are resident tmpfs timings on one member. Cold storage, full-recording performance and solver time were outside the experiment.

The original reader authenticates compressed and index bytes before native consumption and compares the independently computed window and whole-decoded SHA-256 values. The ring also requires complete compressed consumption, processed frame checksum and exact decoded extent. Tests exercise far-backward matches across ring wraps, uneven output windows, retained views, wrong authenticated per-window and decoded-member digest claims, unsupported 16 MiB history, and multiple-frame fallback. **12 component and adjacent tests passed.** [Tests](../../../tests/pipeline_eval/test_fused_window_ring.py) · [Runner](fused_window_ring_trial.py)

## Reproduce

```bash
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
short=/var/tmp/leo-mixed-aperture.pdUjDb1S/build-v2/short-primary.so
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2 \
  env PYTHONPATH="$PWD:$release/src:$release" PYTHONDONTWRITEBYTECODE=1 \
  OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 timeout 100s \
  "$release/venv/bin/python" -BPs -m reports.ALGO08.v3.fused_window_ring_trial \
  run "$short" "$fresh_tmpfs_output"
```
