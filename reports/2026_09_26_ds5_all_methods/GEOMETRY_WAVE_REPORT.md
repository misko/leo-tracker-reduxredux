# DS5 geometry/cone method eligibility

All 42 authoritative recording manifests were checked. None contains a capture-time `receiver_geometry` binding. The corpus uses `radio_pluto_5d4d`; the existing LT3D-001A station resource is bound to a different radio and cannot be inherited after capture.

| Method | Singles | Group8 | Rate-full | Full42 | Position output |
|---|---:|---:|---:|---:|---|
| geometry-fixed-hard-cone | 42 N/A | 5 N/A | 4 N/A | 1 N/A | unavailable |
| geometry-learned-cone-quantiles | 42 N/A | 5 N/A | 4 N/A | 1 N/A | unavailable |
| geometry-staged-full-fov-cone-sweep | 42 N/A | 5 N/A | 4 N/A | 1 N/A | unavailable |
| geometry-local-fitted-full-fov-cone-position | 42 N/A | 5 N/A | 4 N/A | 1 N/A | unavailable |

The machine-readable inference contains 208 explicit `not_applicable_missing_capture_geometry` rows (4 methods × 52 units). No sessions were dropped and no nominal .21 geometry was attached to .20 data.
