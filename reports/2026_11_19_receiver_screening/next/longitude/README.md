# Longitude wrapping in the compact cavity

An opt-in 79-source package completed a synthetic dateline-crossing request that the original 78-source receiver rejected as “geodetic coordinate outside domain.” The wrapped fit was **2.304 km with zero c** and **2.047 km with fitted c** from the simulated receiver. It preserved exact both-arm coordinates, conditional RF RMS, objective values, and scientific work counts on an ordinary in-range recording. Both packages also published a solution **44 km away** under a deliberately incorrect offer. The change repairs the coordinate chart. It does not validate a region offer.

| Request | Original small package | Wrapped zero / fitted error km | Wrapped zero / fitted conditional Doppler RMS Hz | Wrapped wall / monitored CPU s | Cgroup peak MiB |
|---|---|---:|---:|---:|---:|
| Synthetic containing dateline tile | Failed out-of-domain | 2.304 / 2.047 | 77.146 / 77.115 | 24.68 / 24.44 | 269.4 |
| Synthetic far omitted tile | Same false publication | 44.068 / 44.070 | 84.901 / 84.904 | 30.14 / 29.67 | 268.7 |
| Ordinary DS29-0082 in-range control | Exact scientific parity | 2.789 / 2.654 | 106.672 / 106.588 | 28.68 / 26.50 | 273.6 |

The successful synthetic offers used the same 300-second synthetic input with genuine causal TLE history, independent later simulated trajectories and measured GLRT disturbance replay. The source and inputs were sealed before inference. The old package's dateline exception came from its C projector wrapper at initial position selection, and its far result matched both arms of the wrapped package on the exact same request. The authentic in-range control came from the earlier capped small-package series. Each new service ran on one core under 512 MiB with zero swap. The matched controls ran in a separate order, and the positive control failed early, so the times are completion costs rather than a speed comparison.

## Coordinate boundary

The two local charts previously returned an unbounded longitude before the C projector and Python geometry functions, all of which require a legal geodetic longitude. Association also subtracted the two chart longitudes without wrapping. The overlay changes just these three transforms and adds an entry guard. It canonicalizes chart outputs to the half-open interval from −180° to 180°, takes the shortest signed longitude difference when moving from the search tile to the broad-sky chart, and preserves the original arithmetic for the ordinary branch. WGS84 ECEF and ENU rotations, orbital propagation, candidate gates, all scientific fit calls, and the two native C binaries remain unchanged.

The optional chart accepts latitude up to 80° in magnitude, a tile at most 25 km wide, and tile and broad-screen centers at most 150 chart km apart. Tests independently checked the sign and approximate magnitude of local ENU displacements using WGS84 ECEF at the equator, 36° and ±79°, including travel in both directions across the dateline. This preserves the existing small-region linear approximation. Polar charts remain outside its domain. Successful full inference covers one synthetic dateline scene and one previously measured installation. The two synthetic offers share one RF scene, so their endpoint distribution does not estimate field generalization.

- [Source and input protocol](PROTOCOL.md) · [Optional source bundle](receiver-source.tar.gz) · [Exact source hashes and matching numerical binaries](source-lock.json)
- [Prediction seal](prediction-lock.json) · [Actual original dateline controls and errors](control-predictions.json) · [Both-arm scores](scores.csv)
- [Synthetic dateline chart](charts/fitted_c/cavity-longitude-dateline.png) · [In-range control chart](charts/fitted_c/cavity-longitude-roof-control.png) · [Standard figure descriptor](figures.json)
