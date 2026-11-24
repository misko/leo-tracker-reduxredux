# Calibration drawing reuse on the current publisher

The saved weak DS30-0016 publication leaves less than 250 ms of CPU for the proposed calibration drawing reuse. The two calibration arms already share a single position PNG. No new renderer, solve or waveform read was needed to check this at `0458a2af4`. [Combined publication](weak-cairo-combined-DS30-0016.md) · [Calibration layer census](calibration-png-layers.md)

The current combined receipt reports four native orbit PNGs, two native residual PNGs, one track RMS PNG and one position PNG, with no rendering fallbacks. The position and track RMS PNGs are byte-identical to the one-pass Agg control. Both arms of the saved publication preserve the signed terminal, both calibration results, 116 ordered owners and roles per calibration, and the numerical optimizer path and 179-point grid. All eight PNGs were verified at publication. [Combined receipt](measurements/weak-cairo-combined-DS30-0016.json.gz)

| Saved DS30-0016 measurement | CPU |
|---|---:|
| Current complete eight-PNG render and encode | 482.785 ms |
| Four native orbit PNGs including setup and encode | 278.369 ms |
| Orbit encoding within that interval | 132.610 ms |
| All work outside the native orbit interval, by subtraction | 204.416 ms |
| Whole position PNG interval, median of five instrumented one-pass replays | 115.434 ms |
| Whole position PNG interval, observed range | 112.171–208.245 ms |

The current full render took 483.058 ms elapsed. The orbit timer is nested inside that render and covers scene setup, draws and encoding. The remaining 204.416 ms of CPU includes both residual sheets, the track and position PNGs, and unassigned renderer overhead. The four orbit products already draw each channel group's common background once, then restore it for the unassociated view. Both visibility views use the same fitted calibration. Their entire orbit budget outside encoding was 145.759 ms. [Orbit timer](direct_orbit_entry.py) · [Orbit raster reuse](direct_orbit_figures.py) · [Complete render timer](unified_short_bootstrap.py)

In the layer census, changing the fixed-zero endpoint and its RF summary changed only the position PNG. The other seven encoded PNGs were identical. Both position panels already draw the two calibration arms together over one regional background per panel. The overview and detail panels have different affine scales, ticks, clipping and annotations. Even eliminating the whole position interval in every archived replay would miss 250 ms of CPU. The shared calibration background has no second draw to remove. [Per-image timings, pixel digests and perturbation](measurements/calibration-png-layers-DS30-0016.json.gz)
