# Packed fine-spectrum cache experiment

This source-only bundle records the bounded block-floating cache experiment.
The FFT remained FP32. Completed frame spectra were stored as interleaved Q15
real/imaginary components with one FP32 scale per frame, and only the requested
bins were dequantized into the existing FP64 score calculation.

Version 1 used scalar scale scans and packing. Version 2 retained the scalar
host reference and used ARMv7 NEON for four-component peak scans and packing.
Because ARMv7 vector conversion truncates, v2 applies a signed binary32 magic
bias before conversion to preserve nearest-even `nearbyintf` behavior. The
target unit compares scalar and vector results on ties, endpoints, clamp cases,
and deterministic random inputs. Selective-bin dequantization did not change.

The measured ARM mean total CPU times were:

- FP32 raw cache: 4863.0222135 ms per dwell
- scalar packed v1: 6504.785856 ms per dwell
- NEON packed v2: 5167.798311 ms per dwell

NEON recovered most of the scalar packing penalty, but remained 304.7760975 ms
per dwell (6.27%) slower than the FP32 raw cache. The packed-cache candidate was
therefore rejected for speed despite reducing the cached spectrum payload from
eight to approximately four bytes per bin plus one scale per frame.

## Contents

- `fine_pack.h`, `test_fine_pack.c`, and `build.py` are the final v2
  implementation, qualification source, and immutable snapshot builder.
- `receipts/` contains all measured host, sanitized-host, and ARM v1/v2 build
  receipts, including exact compiler commands and hashes for every compiled
  source and binary.
- `selected-source-snapshot.tar.gz` contains one complete v1 C/H source tree.
  Its `v2-overlay/` directory contains the only two source files changed in v2.
  Host and ARM compiled-source hashes are identical within each version, so
  duplicate host and sanitizer source snapshots are omitted.
- `SHA256SUMS` binds every publication artifact.

## Reproduction

In the full research tree, with the immutable
`2026_09_29_arm_fine_precision/builds/{host,arm}-raw-v2` parents present, run:

```sh
python3 reports/2026_09_29_arm_packed_cache/build.py --v2
python3 reports/2026_09_29_arm_packed_cache/build.py --v2 --sanitize
python3 reports/2026_09_29_arm_packed_cache/build.py --v2 --arm
```

The builder refuses to overwrite an existing snapshot. Version 1 is preserved
by the v1 receipts and the complete v1 tree in the archive. To reconstruct the
v2 compiled tree from the archive, extract it, copy `v1/`, then replace
`fine_pack.h` and `test_fine_pack.c` with the files from `v2-overlay/`. The
receipt's `sources` map verifies the result, and its `commands` entries provide
the exact compiler invocation. Compiler and FFTW paths are environment-specific
and may be replaced with equivalent installations when reproducing outside the
original tree.

Run `test_fine_pack` natively for host builds. ARM execution must use the
serialized target runner; do not execute ARM binaries on the host. The build
script itself only cross-compiles ARM artifacts.
