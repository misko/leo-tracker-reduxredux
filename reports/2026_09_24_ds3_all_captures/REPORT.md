# DS3 post-seal evaluation

The reference coordinate is introduced only by the evaluator CLI after inference artifacts are sealed. It is not an inference input.

## Fair scope comparison

| Dataset scope | Best post-seal error (km) |
| --- | ---: |
| DS1 qualified / iteration15 | 0.576 |
| DS2-22 / all22 | 3.039 |
| DS3 / all56 | 4.031 |
| DS3 / geometry5 | 239.344 |

`all56` is the DS3 ordinary-capture scope. `geometry5` is a separate five-capture geometry diagnostic and must not be compared as if it were an all56 model.

DS1's qualified iteration15 value is the published 0.575577 km benchmark. The DS2-22 best includes its qualified fine and follow-up rows and is read from its sealed evaluation artifact; no DS2 value is hand copied here.

## DS3 model results

| Scope | Model | Latitude | Longitude | Error (km) |
| --- | --- | ---: | ---: | ---: |
| all56 | `baseline` | 37.847100 | -122.437528 | 4.231 |
| all56 | `shared-time` | 37.847100 | -122.437528 | 4.231 |
| all56 | `regularized-per-scan-time` | 37.847100 | -122.437528 | 4.231 |
| all56 | `joint_causal_per_norad_orbit_rate` | 37.847100 | -122.437528 | 4.231 |
| all56 | `soft-identity` | 37.847100 | -122.437528 | 4.231 |
| all56 | `consistent-cap800` | 37.848855 | -122.439750 | 4.031 |
| geometry5 | `lt3d_geometry_only` | 38.684921 | -119.959149 | 239.344 |
| geometry5 | `lt3d_fixed_up_cone` | 38.684921 | -119.959149 | 239.344 |
| geometry5 | `lt3d_learned_zenith_cone` | 38.909703 | -119.954306 | 250.181 |
| geometry5 | `global_time_plus_lt3d_cone` | 38.909703 | -119.954306 | 250.181 |

The first five all56 methods converge to the same 4.231 km basin. The consistent cap-800 objective moves about 0.20 km toward the reference and wins DS3 at 4.031 km, but it does not approach the sub-kilometre DS1 result. More observations therefore made this basin repeatable; they did not remove the shared model or association bias.

The geometry arms use only five capture-time-audited LT3D sessions (76 tracks), provisional RX-to-slot mapping, and no receiver phase. They select a remote basin, so they are diagnostics and cannot be ranked against all56. The exact-zero fitted global time offset also means the combined time-plus-cone arm is a validated reuse of the learned-cone result rather than an independent improvement.

## Reproducibility and scope

DS3 freezes 56 terminal-complete scans captured from 2026-09-24 00:00:02Z through 22:20:02Z, as observed at 22:36:58Z. It contains 1,443 eligible tracks and 36,270 observations; DS2-22 is a strict 22-scan subset. The freeze excludes a later 22:30 capture that completed after the declared cutoff.

The DS3 all56 comparison binds six general models: baseline, shared-time, regularized-per-scan-time, joint_causal_per_norad_orbit_rate (from the equal-weight joint artifact), soft-identity, and consistent-cap800 from followups-v2. Per-scan causal-rate and independent-track diagnostics are explicitly excluded. Geometry5 contains exactly the four qualified rows in geometry-model-summary.json.

All inference artifacts were digest sealed before the surveyed reference was supplied to the post-seal evaluator. The machine-readable results are in `evaluation.json` and `comparison.csv`; `postseal-comparison.png` renders the same rows.
