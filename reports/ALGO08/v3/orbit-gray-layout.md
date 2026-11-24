# Gray pixel registration in the saved DS30-0402 orbit sheets

Replaying all four sealed orbit pairs reproduced the two failing gray layers exactly. Both failures are RX1 CH2 in the history-routed DS30-0402 publication. Crop and tint explain **11 of 15** Cairo-to-ordinary misses on the all-observations sheet and **12 of 18** on the unassociated sheet. Giving Cairo the ordinary panel rectangles caused a new failure on the independent DS30-0008 scene. Keep the ordinary orbit renderer available when the frozen visual threshold is required. [Protocol](orbit-gray-layout-protocol.md) · [Receipt](measurements/orbit-gray-layout.json.gz)

## Actual DS30-0402 PNGs

| RX1 CH2 gray layer | Ordinary to Cairo | Cairo to ordinary | Cairo misses with ordinary gray just outside the crop | Cairo misses near low-chroma ordinary pixels | Other Cairo misses |
| --- | ---: | ---: | ---: | ---: | ---: |
| All observations | 357/358, 99.72% | 360/375, 96.00% | 5 | 6 | 4 |
| Unassociated only | 405/406, 99.75% | 407/425, 95.76% | 5 | 7 | 6 |

The reverse-direction miss in each sheet has an exactly neutral-gray Cairo neighbor just beyond the registration crop. The low-chroma column counts dark reference pixels within two pixels when the diagnostic admits up to 15 RGB levels of channel spread. The original visual test still requires identical RGB channels and uses the original crop. All 62 previously passing layers reproduced their scores. Colored support in these two panels was at least 99.98% in both directions. The remaining 4 and 6 misses do not establish a different plotted observation. [Earlier independent pixel diagnosis](orbit-registration-0402.md) · [History-routed source publication](history-risk-cairo-0402.md)

The released Agg template and Cairo request the same `#757575` fill, 0.7 opacity, nominal 11 pt² circular scatter size, and zero marker outline. Both place the gray marks under the orbit curves and draw the opaque associated marks last. The actual RX1 CH2 data rectangle is **260 px** high in Agg and **246 px** in Cairo. Registration scales both to 246 px and resamples edge coverage. Thin orbit strokes and their antialiasing can then cover different subpixels of a translucent mark. Agg also uses default projecting caps, round joins and a 0.8 pt grid at 0.18 opacity. Cairo uses its default stroke geometry and a one-pixel opaque gray grid that renders darker on white. The archived Cairo artist witness confirms the live lane had **52 gray observations and 24 orbit curves**. It stores hashes and shapes of the calibrated coordinate arrays. The original arrays were not retained for a direct redraw of this DS30-0402 scene. [Cairo path](direct_orbit_figures.py) · [Release orbit template](../../../src/leo/presentation/orbit_plot.py)

## Generic geometry prototype on the independent DS30-0008 scene

Used the genuine retained calibrated lanes and constructed the original panel rectangles with the original Agg template. Substituted those rectangles on every Cairo panel and kept all data, exposure, colors, stroke and marker properties, native ticks and painter order. The same original scene supplied an independent shared Agg draw and an unmodified Cairo draw. All four output dimensions matched. No fitted values were regenerated. [Source scene and its scientific provenance](direct-orbit-figures.md)

| DS30-0008 orbit sheet | Minimum gray bidirectional support, current | Minimum gray bidirectional support, aligned |
| --- | ---: | ---: |
| CH1–4 all observations | 98.095% | 97.604% |
| CH1–4 unassociated only | 98.724% | 99.427% |
| CH5–8 all observations | 99.263% | 99.315% |
| CH5–8 unassociated only | 99.216% | 99.193% |

The CH1–4 all sheet gained one previously passing gray-layer failure at RX2 CH4. Ordinary-to-Cairo support improved from **98.75% to 99.46%** and Cairo-to-ordinary support fell from **98.10% to 97.60%**. The remaining 63 gray and color layers passed. The original Agg artist and geometry construction adds **0.830 CPU s** to the aligned pipeline. Cairo scene construction was 0.041 CPU s, and painting the four sheets to decoded RGB without PNG encoding took 0.741 CPU s in ordinary Cairo geometry or 0.729 CPU s aligned. These are isolated plot scopes from one shared low-priority CPU 2 slot. The test does not support charging ordinary layout work as a general Cairo correction.

The active renderers and acceptance criterion are unchanged. This replay opened neither waveform nor backing archive and ran no solve or orbit propagation. The reproducible command is `orbit_gray_layout_trial.py FRESH_TMPFS_RECEIPT.json` under the same low-priority lock and installed environment as the saved Cairo transfer. The as-run driver is commit `47768cc3c`. The JSON receipt's uncompressed SHA-256 is `ff056fb7cdfcdb0dfeebf6ad6faeee6444a57a6b868f39c47db8b5c52d82dd9a`. Seven focused component tests passed. [Driver](orbit_gray_layout_trial.py) · [Component tests](../../../tests/pipeline_eval/test_orbit_gray_layout_trial.py)
