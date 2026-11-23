# Native shared orbit drawing in complete saved publication

On weak DS30-0016 the corrected Cairo renderer cut the full eight-figure render from **0.879 to 0.506 CPU seconds**. The existing control finished in **5.169 s elapsed** and the corrected candidate **4.718 s** through exit. The control included a measured **47.8 ms CPU** live-scene export for independent verification. Subtracting that export leaves a **0.402 s CPU** difference. The corrected candidate used the normal active entry without scene export or an audit renderer. On dense DS30-0008 the one instrumented full-length transfer established scientific parity and a working native draw. Its cross-run clocks did not establish an end-to-end gain. [Frozen protocol](direct-orbit-figures-protocol.md) · [Corrected weak process and both render replays](measurements/direct-orbits-corrected.json.gz)

## Why the four orbit sheets

| Remaining official weak template | Saved reference interval, CPU ms |
| --- | ---: |
| CH1–4 all observations | 225.4 |
| CH5–8 all observations | 216.0 |
| Position map with both calibration arms | 118.3 |
| CH1–4 unassociated | 54.8 |
| CH5–8 unassociated | 53.8 |
| Track RMS | 35.0 |

The four orbit products total **550.1 ms**, including **136.2 ms** of encoding. The incumbent already draws two shared orbit bases. The candidate uses that same grouping, retaining one fresh Cairo background per band and applying the two title, scatter and footer overlays before the existing libdeflate encoder. It uses the installed wrapped-CFO and alias-gap functions and satellite palette, and builds every line, point and label from the live calibrated lanes. The candidate does not construct Matplotlib orbit artists. The scene still uses the installed data types and color lookup. [Reference intervals](direct-residual-figures.md) · [Orbit scenes and Cairo code](direct_orbit_figures.py)

The optional `--direct-orbit-figures --one-pass-web-png` route loads the adapter inside the active render call. The original source and encoder bindings are checked. The original renderer remains the fallback when the inputs, geometry, native library or encoding are unsupported. The weak pair enables the already-qualified two native residual sheets in both processes. The dense transfer retains the archived control's incumbent residual renderer, so only its four orbit files differ. [Active boundary](unified_short_bootstrap.py) · [Adapter](direct_orbit_entry.py)

## Saved process clocks

| Weak stage | Control | Corrected candidate |
| --- | ---: | ---: |
| Full scientific solve CPU | 2.676 s | 2.671 s |
| Render and encode CPU | 0.879 s | 0.506 s |
| Four native orbit products, including encoding | — | 0.296 s |
| PNG encoding within the four native products | — | 0.147 s |
| Process CPU through exit | 5.166 s | 4.716 s |
| Process elapsed through exit | 5.169 s | 4.718 s |

The first instrumented weak pair, control first, measured **5.169 → 4.564 s elapsed** and passed the 0.150 s continuation gate. Both children exported the same 38,480-sample scene. The control recorded 128 dependency input blocks and one major fault. Its candidate was faster outside rendering too. Visual inspection found the long “Unassociated” label touching the next legend column, so the retained implementation measures the widest label in each column. A single fresh corrected weak candidate supplied the final clocks above. Both corrected sheet pairs reserve at least **26 pixels** from the preceding glyph extent to the next column origin. Representative corrected weak and dense charts were inspected. [Initial weak pair](measurements/direct-orbits-weak-instrumented.json.gz)

The dense instrumented candidate took **29.880 s elapsed / 29.732 CPU s**. The earlier same-packet installed comparison took **26.926 / 26.905 s**. The candidate solve was 24.707 CPU s versus 22.792 s in the earlier process. Independent scene capture of its 519,572 curve samples added **0.926 CPU s** inside the timed process. The capture is trial-only. Full rendering took **2.236 CPU s** in the candidate and **2.355 s** in the archived control. The native orbit component took **0.979 s**, including **0.242 s** of encoding. A corrected repaint from the sealed scene took **0.987 CPU s** and included the corrected legend. No dense solver was repeated after that layout correction. These cross-run clocks give no dense publication speedup estimate. [Dense instrumented transfer](measurements/direct-orbits-dense-instrumented.json.gz)

## Exact scientific scene and raster changes

The independent stock artist check preserved every folded observation, curve sample and alias gap, series order and color, title and count, both limits, units, 94 visible tick labels, and ordered legend labels in each case. The weak scene contains **475 observations, 32 orbit curves and 38,480 curve samples**. Dense has **7,336 observations, 432 orbit curves and 519,572 samples**. The publication retained the complete 179-point grid, original path, terminal, and **116 / 4,367** owner and role rows per calibration arm in weak / dense. Both position sidecars continued to bind their byte-identical position PNG.

| Saved case and calibration | Original and retained latitude, longitude | Original and retained RF RMS |
| --- | --- | ---: |
| Weak fixed zero | 37.83878569°, −122.49308768° | 121.526 Hz |
| Weak fitted | 37.84003085°, −122.50129726° | 120.291 Hz |
| Dense fixed zero | 37.84151644°, −122.48146834° | 140.961 Hz |
| Dense fitted | 37.84182527°, −122.48236394° | 140.950 Hz |

All eight weak corrected official files passed content-address and decoded RGBA verification. The four native orbit files exactly match an independent corrected replay of the sealed live inputs. The other four files matched their control byte and pixel hashes. The dense instrumented process also preserved the four ancillary byte and pixel hashes. The corrected dense raster differences below come from render-only replays. All sheets retain original image mode, size, DPI and metadata.

| Corrected orbit PNG | Weak changed pixels / RGB MAE | Dense changed pixels / RGB MAE |
| --- | ---: | ---: |
| CH1–4 all observations | 7.93% / 3.83 | 23.01% / 6.39 |
| CH1–4 unassociated | 7.80% / 3.87 | 22.52% / 6.37 |
| CH5–8 all observations | 7.94% / 3.83 | 23.27% / 6.44 |
| CH5–8 unassociated | 7.85% / 3.88 | 22.83% / 6.42 |

The new rasters include Cairo stroke and glyph antialiasing, slightly different grid weight and a simpler legend without a frame. The four files add **187,517 bytes** on weak and **698,725 bytes** on dense. The unchanged values and distinct pixels are recorded separately. Twenty-one component and adjacent tests passed. [Tests](../../../tests/pipeline_eval/test_direct_orbit_figures.py)

## Reproduce

The initial `run weak` and `run dense` receipts bind revision `5257e8f67`. The current `correct` subcommand uses those same private tmpfs roots and prepares one corrected weak candidate plus render-only verification of both saved scenes. The normal prototype options are `--direct-orbit-figures --one-pass-web-png`. No recorded waveform is opened during these saved comparisons. Use a private tmpfs root and an account permitted to read the signed acquisition metadata and causal assets.

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2 \
  env PYTHONPATH="$PWD/reports/ALGO08/v3:$PWD:$PWD/src:$release/src:$release" \
  OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  "$release/venv/bin/python" -BPs reports/ALGO08/v3/direct_orbit_figures_trial.py \
  correct "$fresh_output" "$weak_probe_root" "$dense_probe_root"
```
