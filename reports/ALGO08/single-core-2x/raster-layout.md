# Single-core layout reuse for all eight publication figures

The prototype saved **0.44 CPU seconds on DS30-0016** and **0.41 CPU seconds on the northern near-edge simulation** relative to the shared-pixel renderer. All eight PNGs on each recording had identical decoded pixels, dimensions, color mode, metadata and encoded bytes. The shared-pixel control also reproduced every original publication hash.

| Saved detection packet | Observations | Render CPU, shared pixels → layout | CPU speedup | Render elapsed, shared pixels → layout | Encoded bytes in either arm |
|---|---:|---:|---:|---:|---:|
| DS30-0016 physical | 440 | 2.427 → 1.990 s | 1.22× | 2.501 → 2.047 s | 2,818,750 |
| Northern simulation, 100 m inside offer | 456 | 2.779 → 2.368 s | 1.17× | 2.845 → 2.430 s | 5,079,659 |

The table averages two runs per arm. The figures include the regional map and every fitted-c diagnostic. Both renderers received the same fixed-zero and fitted-c positions and recorded paths. [Physical receipt](measurements/raster-layout-DS30-0016.json) · [Northern receipt](measurements/raster-layout-north-edge.json)

The trial draws the retained orbit column directly and reuses automatic ticks while their view limits and available tick space remain fixed. Both orbit views still use the existing static raster reuse. Residuals, track RMS and the regional position map use the existing draw calls. Satellite colors, every point and curve, layout measurements, axis limits, legends and image encoding come from the publication renderer. [Trial renderer](../../../tools/pipeline_eval/variants/experimental/raster_layout.py)

The retained axes start in the first column of the original gridspec so shared ticks and row geometry follow Matplotlib. The trial checks that the discarded title cannot increase the row bounds and that the original two columns could fit horizontally. The original publication renderer sets the final single-column width. The tight-layout pass reuses identical axis bounds before moving any axes. Versions, styles and geometries outside the prototype's checks use the shared-pixel renderer. No location, observed range, row count, satellite list or title from either timed recording is stored in the trial. A component test compares all eight outputs on a synthetic southern-hemisphere frame with a 185 km offer, unequal orbit group heights, a partial grid and an evaluation reference. Additional tests exercise the style and geometry fallbacks. [Component tests](../../../tests/pipeline_eval/test_experimental_raster_layout.py)

## Reproduction

For each recording, the trial verifies the saved detection file digest, reconstructs one packet with the published region and capture-era archive, and verifies both coordinates against the frozen publication. Neither arm reads raw I/Q or changes the packet. Rendering runs twice per arm in reversing order on CPU 2, with low CPU and I/O priority and one numerical thread. Each image is fully decoded and compared by pixel, dimension, mode and metadata. The trial also compares the encoded hashes to the original publication receipt. Comparison work and packet reconstruction are outside both render timers. The renderer patch is scoped to the serial experiment. [Trial harness](raster_layout_trial.py)

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
bench=/tmp/leo-algo08v2-2x-bench
flock "$bench/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
  env PYTHONPATH="$PWD:$release/src:$release" OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  "$release/venv/bin/python" -BPs reports/ALGO08/single-core-2x/raster_layout_trial.py \
  "$detections" "$pair" "$archive" "$release/assets" "$detection_sha256" --first "$first"
```

Use the DS30-0016 pair from `integration-deferred` and the northern near-edge pair from `integration-moments-v2`. Set `first` to `shared-pixels` for DS30-0016 and `layout` for the northern simulation. The physical archive is `/var/lib/leo/tle`, which requires the release service account on Gauss. Insert `sudo -n -u leo` immediately before `env` for that run. The simulated archive is the existing public panel's `tle` directory. The measured interval is rendering from saved detections. [Original physical and near-edge pair descriptions](moments-publication.md)
