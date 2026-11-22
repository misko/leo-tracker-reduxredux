# Lossless encoding of the eight ALGO08v2 publication figures

Libdeflate level 3 saved **0.46–0.53 CPU seconds in encoding** on each saved packet and **0.43–0.62 CPU seconds in the full renderer**. The PNG payload fell by 2.6–7.1%. All 24 figures reproduced every decoded RGBA byte, including the labels and plotted marks, with the original dimensions, DPI and PNG text. The control reproduced all 24 publication hashes. The candidate files have new encoded hashes, and their PNG chunk CRCs verified. [Measurements and image digests](measurements/lossless-png.json)

| Saved development packet | Encode CPU, Pillow → libdeflate | Render CPU, Pillow → libdeflate | Render elapsed, Pillow → libdeflate | Total bytes, Pillow → libdeflate |
|---|---:|---:|---:|---:|
| DS30-0016 physical | 0.622 → 0.165 s | 1.883 → 1.455 s | 1.916 → 1.480 s | 2,818,750 → 2,618,651 |
| Northern public near edge | 0.731 → 0.213 s | 2.287 → 1.830 s | 2.356 → 1.881 s | 5,079,659 → 4,949,839 |
| Southern public near edge | 0.720 → 0.188 s | 2.264 → 1.646 s | 2.356 → 1.661 s | 5,107,887 → 4,965,792 |

Each entry averages two renders in a fresh process per arm. The physical and northern runs began with level 3, and the southern run began with the control. Both arms used the guarded layout renderer and the same reconstructed, selected packet. The timed interval began after reconstruction and ended before ordinary Pillow decoding and comparison against the saved artifacts. The harness verified the detection digest and both position endpoints before drawing. [Timing and decode harness](lossless_png_trial.py)

## Encoding costs and memory

The native filter uses PNG Sub and Up on the Agg RGBA buffer. It selects the smaller sum of absolute signed byte differences for each row, with a direct zero-fill for identical adjacent rows. Matplotlib and Pillow produce the existing text and DPI chunks. The encoder copies those chunks and writes a standard zlib stream, preserving the original 8-bit RGBA representation. Scalar filtering applies where the CPU lacks SSSE3. Missing native support or inputs outside the contiguous, upper-origin RGBA path use the original writer. [Native filter](../../../tools/pipeline_eval/variants/experimental/lossless_png.c) · [Renderer hook](../../../tools/pipeline_eval/variants/experimental/lossless_png.py) · [Component tests](../../../tests/pipeline_eval/test_experimental_lossless_png.py)

| Level 3 CPU per eight images | DS30-0016 | North | South |
|---|---:|---:|---:|
| Row filtering | 26 ms | 45 ms | 27 ms |
| Compression | 136 ms | 163 ms | 157 ms |
| Header, chunks and checksums | 3 ms | 5 ms | 4 ms |
| Remaining renderer work | 1.290 s | 1.617 s | 1.457 s |

The northern comparison gave 0.290 s for level 1, 0.213 s for level 3 and 0.209 s for level 6, with 5.025, 4.950 and 4.870 MB of PNG output. Scalar level 3 used 0.214 s with the same PNG bytes. The measured gain came primarily from libdeflate. Level 3 was the setting exercised on all three packets.

The encoder holds one filtered image at a time. The largest measured scanline buffer was 29.38 MB, plus a 9.6 kB temporary row, the compressor workspace and its output buffer. The compressed output allocation reserves the worst-case size and NumPy leaves its untouched pages uninitialized. Process peak RSS was 614–945 MiB across the controls and level-3 runs. Every peak had already been reached during the saved solver reconstruction, so those process peaks cannot isolate the render-only memory difference.

The previous frozen DS30-0016 and southern runs needed another 1.22 and 0.89 CPU seconds to reach 2×. Subtracting the isolated encoding gain leaves about 0.76 and 0.36 seconds respectively. The northern full-search run needed 1.86 CPU seconds, of which this change could cover about 0.52. These are stage-based estimates from already saved development packets. [Frozen comparison clocks](full-search-publication.md)

## Reproduction

Build the optional filter, then use the existing pair, saved detections, archive and detection digest in the measurement file. Execute from the research worktree. Use `sudo -n -u leo` immediately before `env` for the physical archive.

```sh
bench=/tmp/leo-algo08v2-2x-bench
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
cc -O3 -shared -fPIC -std=c11 -Wall -Wextra -Werror -pedantic \
  tools/pipeline_eval/variants/experimental/lossless_png.c -o "$bench/lossless-png.so"
flock "$bench/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
  env PYTHONPATH="$PWD:$release/src:$release" OPENBLAS_NUM_THREADS=1 \
  OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 "$release/venv/bin/python" -BPs \
  -m reports.ALGO08.single-core-2x.lossless_png_trial \
  "$detections" "$pair" "$archive" "$release/assets" "$detection_sha256" \
  --repeats 2 --library "$bench/lossless-png.so" --level 3
```

Omit `--library` for the Pillow control. The freezer accepts `--rendering lossless-raster --png-filter LIBRARY SHA256 --png-deflate LIBRARY SHA256`. It copies both reviewed libraries, pins them in the source manifest and verifies the copy again before loading the renderer. The measured system runtime was libdeflate `1.23-2ubuntu1`. [Exact filter and runtime hashes](measurements/lossless-png.json)
