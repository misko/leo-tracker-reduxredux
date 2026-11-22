# Receiver height in the two-dimensional regional solver

The supplied latitude, longitude and search width control localization, but the active solver also makes a geographic assumption that has no station name attached. Its regional sky screen evaluates the observer at **zero metres above the WGS84 ellipsoid**. The Doppler projection used for phase fitting defaults to the same height. The current regional offer has no height field. The public two-site I/Q generator does vary the planted height, but its original range is only **25–110 m**. [Orbit screen](../../../src/leo/analysis/localization_v3/orbits.py) · [Phase projection](../../../src/leo/analysis/research/phase_linear_geometry.py) · [Region contract](../../../src/leo/contracts/algo08_region.py) · [Waveform generator](../../../tools/pipeline_eval/qualification/waveform_site_model.py)

We held latitude, longitude, satellite trajectories, RF and observation times fixed and changed only receiver height. The input was one saved orbital catalogue. For each site we kept every satellite that was usable and at least 10° above the horizon at every sampled time over five minutes. Each entry is the median of the per-satellite RMS difference between the 1,000 m and zero-height Doppler predictions at 11.5 GHz.

| Receiver coordinates (lat, lon) | Satellites | Raw difference | After removing a per-satellite constant | After removing a per-satellite constant and linear drift |
|---|---:|---:|---:|---:|
| 15°, 75° | 21 | 118.83 Hz | 117.09 Hz | 60.38 Hz |
| −25°, −65° | 29 | 116.45 Hz | 116.21 Hz | 62.32 Hz |
| 65°, 120° | 7 | 114.74 Hz | 107.82 Hz | 59.90 Hz |

At 100 m, the three raw medians were 11.47–11.88 Hz. At 2,000 m, they were 229.49–237.65 Hz. The constant and drift subtractions are descriptive least-squares projections on each satellite's own trajectory. The result shows that height can change Doppler shape even after removing a linear trend. It does not measure horizontal position error, ambiguity between satellites or the benefit of adding a height parameter to the solver. All receiver coordinates and heights appear only in this kinematic experiment. [All heights and timings](measurements/height-sensitivity.json) · [Reproduction script](height_sensitivity.py)

Run `height_sensitivity.py PATH_TO_TIMESTAMP-DIGEST.tle` with the scientific release interpreter. The script verifies the saved catalogue digest and propagates all tracks once. It consumes no recorded I/Q or localization results. The coordinates were chosen as three geographic examples, without searching for an extreme result.
