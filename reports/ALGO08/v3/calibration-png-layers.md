# The web figures already share the calibration map draw

The active DS30-0016 renderer emitted **eight PNGs from six Agg draws**. Seven plots consume fitted-calibration data. The eighth is one position map that draws both calibration arms together. Moving only the fixed-zero endpoint and changing its RF summary on a private copy changed the decoded map and left the other seven PNGs byte-for-byte identical. The measurement found no second calibration background to reuse. [Sealed layer census](measurements/calibration-png-layers-DS30-0016.json.gz) · [Protocol](calibration-png-layers-protocol.md)

## Paid rendering work

| PNG | Output interval CPU, ms | Base Agg draw, ms | Encode, ms | Original pixel dimensions |
|---|---:|---:|---:|---|
| CH1–4 orbit, all | 220.2 | 118.1 | 34.1 | 2400 × 3022 |
| CH1–4 orbit, unassociated | 54.2 | 0.0 | 33.6 | 2400 × 3022 |
| CH5–8 orbit, all | 213.5 | 118.5 | 32.7 | 2400 × 3022 |
| CH5–8 orbit, unassociated | 53.1 | 0.0 | 32.5 | 2400 × 3022 |
| CH1–4 residuals | 159.6 | 123.2 | 11.3 | 1875 × 1375 |
| CH5–8 residuals | 159.1 | 122.9 | 11.2 | 1875 × 1375 |
| Track RMS | 33.8 | 23.2 | 6.3 | 2000 × 750 |
| Position | 115.4 | 92.5 | 8.0 | 1680 × 960 |

Each cell is the median of five instrumented renders on the same saved physical packet. An output interval starts at construction of its figure or completion of the preceding encode for a shared figure. It ends when that image's encode completes. The remaining bundle CPU had a median of 63.0 ms and includes work between figures and final cleanup. These independently computed medians do not sum to the median bundle CPU. The interval for each unassociated view includes restoring the existing raster and drawing the changed overlays. Both unassociated views reused the base raster of their all-observation view. The orbit pair compares observation visibility under one fitted calibration. [Per-image stream and timing receipt](measurements/calibration-png-layers-DS30-0016.json.gz) · [Previously qualified layout and orbit reuse](one-pass-web-png.md)

The five plain renders used a median **1.183 s CPU**, range 1.153–1.249 s. The five profiled renders used a median **1.161 s CPU**, range 1.155–1.290 s. Runs alternated which condition went first under the Gauss lock on CPU 2. The paired instrumentation ratio was 0.996 at the median and ranged from 0.929 to 1.090. The comparison estimates measurement overhead. It supplies no renderer speedup claim. [Instrumentation](calibration_png_layers.py)

## Position map layers and verification

Each position panel contains both estimate markers and both recorded trajectories. Fitted calibration uses a red diamond and solid crimson paths. Fixed-zero uses a blue square and dashed blue paths. Each panel draws the regional centre, gridlines, and its arm-independent ornaments once. The left panel has the 179-point fitted-objective scatter and colorbar. The right panel has its own axis titles and phase-round annotations. The map's left and right affine scales are **20.90 and 548.99 px/km**. The axes use **5 km and 0.2 km** x-axis tick spacing, respectively. Even when a trajectory shares data between the panels, its clipping, transforms, ticks and surrounding labels differ.

The entire map interval is only **115.4 ms**, about **9.8%** of the plain eight-PNG median and **1.34%** of the prior 8.630 s complete weak raw-process CPU. Those are ceilings from pretending the whole map interval were free. Both arm-specific overlays and their shared background are already in the same draw, so this study found no arm-split raster savings to test. A second dataset and an adapter were outside the eligible follow-up. [Measured weak raw process](unified-short-layout.md)

The replay matched both calibration arms, ordered owners and roles, grid, and optimizer path. The ordinary store published the eight explicit-layout PNGs. Independent full decoding reproduced all eight reviewed RGBA digests, dimensions, modes and metadata. The position grid and path matched the original scientific documents and each pointed to the actual stored position PNG. The fixed-zero perturbation was an untimed in-memory probe. The perturbed picture never entered publication or scoring, and the replay read no waveform samples. Seven focused tests passed. [Raw receipts and PNG digests](measurements/calibration-png-layers-DS30-0016.json.gz) · [Tests](../../../tests/pipeline_eval/test_calibration_png_layers.py)
