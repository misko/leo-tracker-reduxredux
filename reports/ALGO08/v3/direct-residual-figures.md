# Native drawing of the two weak residual figure sheets

Rebuilding the two residual charts in Cairo reduced their measured render-and-encode work from **406.7 to 52.6 CPU ms** on one fresh saved DS30-0016 publication. The **354.2 ms** reduction is at the component boundary. The measured process took **5.776 s elapsed / 5.773 CPU s** with both residual render paths and audit work and exited with status zero. Both calibration arms, the original owner and role rows, the 179-point grid, the path, and six unmodified official PNGs matched the archived publication. [Frozen protocol](direct-residual-figures-protocol.md) · [Receipt and official image digests](measurements/direct-residual-figures-DS30-0016.json.gz)

## What a direct renderer could remove

The earlier active import census attributed **93.5 CPU ms** exclusive to Matplotlib and its submodules. The first plot-module import took **134.3 ms** inclusive under the position solver's orbit scene types. The process never imported `pyplot`. The solver also loaded SciPy linear algebra and stats. Its measured **317.5 ms** exclusive SciPy dependency cost includes numerical work and remains in the eligible solver. Replacing the residual renderer while retaining the other six charts leaves those already-paid imports in the process. A small standalone scene-and-raster smoke run loaded neither Matplotlib nor SciPy. [Original import census](active-imports.md)

The prior explicit-layout weak bundle had a **1.183 CPU s** median. The fresh control in this probe took **1.171 s** excluding the added reference inventory. Within that fresh bundle, six Agg draws took **605.3 ms**, eight existing PNG encodes **173.7 ms**, and the balance **392.3 ms**. Before replacing drawing, rebuilding all scene data, transferring pixels, and maintaining metadata, **997.6 ms** is the most this measured bundle could shed if existing encoding were held fixed and everything else were free. It is a deliberately optimistic ceiling. Independent decoding and RGBA verification of the eight official products previously took **311.7 ms** at its separate saved publication boundary. [Explicit-layout layers](calibration-png-layers.md) · [Fixed publication work](saved-overhead.md)

The two original residual sheets took about **319 ms** at the sum of their prior per-chart medians. In this probe their fresh figure intervals took **247.4 and 159.4 ms**, with **124.8 and 123.6 ms** in Agg draw. The first sheet's setup explains most of the difference from that historical sum. Their observed no-encode ceiling in the fresh process was **383.6 ms**.

| Scope across both residuals | Reference CPU ms | Direct CPU ms |
| --- | ---: | ---: |
| Import and native initialization | Already present in the worker | 2.84 |
| Scene construction | Included in reference intervals | 0.27 |
| Agg drawing or Cairo raster and pixel transfer | 248.40 | 25.20 |
| Same libdeflate PNG encode | 23.14 | 24.24 |
| **All timed component work** | **406.72** | **52.55** |

This pair adds 4.8 ms of reference inventory, timed separately, and 83.4 ms of diagnostic decode and hash for both styles. The active official publication still performed its own figure verification. The trial built both new scenes after the unmodified reference render, from the same fresh plotting packet. Only the two independently verified residual PNGs were substituted at the official publication port. A renderer that skips the original residuals entirely has not been timed through fresh process exit. [Fresh saved runner](direct_residual_figures_trial.py)

## Scientific and visual comparison

Cairo drew the original two 1,875 × 1,375 sheets at 125 DPI without plotting artists. It reused the packet's fitted-calibration residuals, original satellite order and colors, and original title context. It preserved the ordered time and CFO of every scatter point, all 16 axes' limits and labels, the 16 zero lines, and the measurement counts. All 116 points in this particular fix fell in CH1–4. CH5–8 has no associated scatter points, with all eight empty lanes still showing their axes and labels. The other six published charts preserve the original orbit legends, residual-independent imagery and map bindings. [Standalone scene and drawing code](direct_residual_figures.py)

The exact comparison found 13 differing tick sets across the 32 axes. They coincide with the 13 empty panels' y axes. A separate reproduction of the empty axis preserved all five formatted tick labels and found a largest position difference of **1.39 × 10⁻¹⁷ Hz** from floating-point tick construction. The three populated panels' marks and limits match. The output comparison found **9.68% / 9.92%** changed pixels and mean absolute RGB differences of **6.80 / 6.71** on the 0–255 scale. Cairo produced a slightly darker grid and different glyph and stroke antialiasing. Visual review of the populated comparison found no clipped labels. The two new encoded files total 441,411 bytes, up **109,169 bytes** from 332,242. They keep the original RGBA mode, dimensions, DPI and PNG metadata. This is a scientific-content-equivalent rendering, with visibly different raster pixels.

All eight outputs passed the standard store's file and decoded RGBA checks. The position image stayed byte-identical and both its grid and path sidecars still bind its original content digest. Nine component and adjacent tests passed. The native binding is a research prototype using the local little-endian Cairo runtime. [Tests](../../../tests/pipeline_eval/test_direct_residual_figures.py)

## Reproduce

Use a fresh private tmpfs parent and an account permitted to read the sealed signed inputs. The independent verifier uses the repository storage contract. The child publishes through the pinned installed tools.

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2 \
  env PYTHONPATH="$PWD/reports/ALGO08/v3:$PWD:$PWD/src:$release/src:$release" \
  OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  "$release/venv/bin/python" -BPs reports/ALGO08/v3/direct_residual_figures_trial.py "$output"
```
