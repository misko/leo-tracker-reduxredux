# Approximate terrain-plus-mount height: failed accuracy screen

The operator confirmed the antennas are approximately10ft above local ground.
At the unchanged saved roof coordinates, terrain54.571628571m plus3.048m gives
57.619628571m approximate orthometric height. Applying the saved GEOID18
separation -32.477m gives25.142628571m NAD83 ellipsoidal height, used here as an
explicit approximation to the model's WGS84 height. The exact NOAA VDatum
conversion returned errors. This is not a surveyed or exact-frame height.
The newer rounded Compass coordinates and invalid phone elevation do not
replace the original horizontal reference or historical metadata.

Height and the two-record screen were frozen before fitting. Original causal
orbit banks, observations, masks and candidate mixtures were retained. Each
arm used original IID and zero seeds; qualified training-score selections were
sealed before geographic assessment. No height was optimized or selected using
position error. This calibration was supplied after capture and is labeled as
newly station-calibrated reanalysis, not historical online performance.

| Original scan index | Refitted zero-height error | Calibrated-height error | Change |
|---|---:|---:|---:|
| 0 | 765.072 m | 857.323 m | +92.251 m |
| 16 | 2153.140 m | 2167.814 m | +14.674 m |

Both selected calibrated fits qualify, but neither improves. The prespecified
screen fails, so this variant is not extended or promoted as an accuracy gain.
This does not establish that the physical antenna height is wrong or justify
fitting a nonphysical height to compensate for other model errors. The result
only tests this approximate height correction on these two diagnostic scans.
Four reused component tests pass for fixed-height gradients/held isolation and
training-only qualified selection. All eight children terminate successfully.
No production defaults or golden fixtures changed; no new RF was collected.
