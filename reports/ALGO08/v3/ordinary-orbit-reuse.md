# Exact reuse inside the ordinary Agg orbit sheets

The installed renderer already uses one axes build, tight layout and Agg background per band. Both orbit views share that background. The first full-buffer restore in each band immediately follows its snapshot and takes **6–7 ms CPU total**. Skipping those two restores reproduced the four ordinary orbit PNGs byte for byte on both saved physical scenes. Even granting free second-band axes construction and tight layout plus removing every snapshot and restore, the measured gross CPU budgets were **119 ms on DS30-0402 and 97 ms on DS30-0016**. This is below the frozen 0.2 s screen. [Protocol](ordinary-orbit-reuse-protocol.md) · [Receipt](measurements/ordinary-orbit-reuse.json.gz)

| Installed renderer CPU | DS30-0402 | DS30-0016 |
| --- | ---: | ---: |
| Four orbit sheets | 1,070 ms | 629 ms |
| Two base draws | 264 ms | 196 ms |
| Four PNG encodes | 231 ms | 128 ms |
| Every copy and restore | 39.9 ms | 20.2 ms |
| Two provably redundant restores | 6.7 ms | 6.0 ms |
| Second tight layout | 63.4 ms | 61.1 ms |
| Second band's subplot construction | 15.4 ms | 15.3 ms |
| Gross budget for all copies/restores, second layout and axes | 118.8 ms | 96.6 ms |

The paired views use the same layout and save one base draw per band already. The installed call draws the static grid, gray observations, orbit lines, and legend once. It paints the original titles and footer, and in the all-observations image it adds the associated points. The second restore removes those overlays before the second view. The prototype elides only the first restore under the exact released call sequence, with the same full captured region, canvas and renderer. The original paint, alpha, stroke ordering, clipping and lossless PNG encoder still execute. Both modes reproduced all eight archived ordinary file hashes. The four orbit files were also independently decoded to equal RGBA hashes and original PNG metadata. The recorded axes, titles and legend were identical between modes. [Existing shared orbit route](history-risk-residual-layout-0402.md)

The two bands shared all eight pairs of axis rectangles, limits and axis labels on each scene. Their channel and count titles differ. There were **zero cross-band matches among 192 folded paths per band** on DS30-0402 and **zero among 16 per band** on DS30-0016, even before requiring matching transforms or clipping. The exact path census itself costs 20.9 and 2.0 ms CPU, respectively. Reusing panel geometry alone would still need the distinct data layers and the separate overlays. The gross budgets credit all copy and restore time even though some background preservation is required. Drawing static furniture separately across bands would need separate evidence because it currently shares the same base draw with the different data layers. [Earlier layout and draw reuse](one-pass-web-png.md) · [Existing overlay timing](calibration-png-layers.md)

The measured complete orbit scope changed from **1.070 to 1.088 s CPU** on DS30-0402 and from **0.629 to 0.589 s CPU** on DS30-0016. Both figures include the layout, cache construction and encoding. The changes exceed the directly timed removable cost and come with changes in base-draw CPU. This single opposite-order pair per scene cannot establish a marginal complete-render saving. No active renderer change is proposed.

The one microbenchmark used saved live scenes from the completed DS30-0402 residual-layout and DS30-0016 frame-portable publications under the shared Gauss CPU 2 lock, nice 15, I/O priority 7 and one numerical thread. No solver, waveform or backing archive ran. Reproduce with `ordinary_orbit_reuse.py FRESH_TMPFS_RECEIPT.json` in the installed environment. The benchmark used frozen commit `4039ece6f`. The receipt's uncompressed SHA-256 is `b18cdf218655041f4394d3423da09bea71d53938511f1946ef30a31e4ad2f0ce`. Twenty-one component and neighboring tests passed. [Driver](ordinary_orbit_reuse.py) · [Tests](../../../tests/pipeline_eval/test_ordinary_orbit_reuse.py)
