# Continuous receiver margin in Graph path discovery

The frozen reward improved North horizontal error from **0.682/0.158 km to 0.556/0.105 km** in fixed/fitted calibration. It kept every final owner, satellite ID and role. The fixed arm still had **450 m additional error against named v3**, above the 250 m transfer gate. DS30-0016 preserved its exact **0.501/0.997 km** outcome. The two-recording gate stopped the study before South. [Frozen protocol](discovery-margin-protocol.md) · [Full saved and graph timing receipts](measurements/discovery-margin.json.gz)

## Rule and native controls

The 8 ms primary runs its signed scout confirmation and checks the refined pilot with the independent fractional exact-versus-rolled control statistic. Its verified factor carries the same `exact - control` used by the native **0.025** acceptance gate. The rule assigns a selected nonanchor node weight of `clamp(1 - 0.025 / margin, 0, 1)` and gives each 20 ms anchor unit weight. The reward is a monotone heuristic. The margin does not estimate posterior correctness, and no surveyed position, owner, continuation label or second-aperture result enters the weight. North retained all 1,595 selected measurements including 82 anchors. DS30-0016 retained all 506 including 74 anchors. Both scorer checks reproduced the original signed packet digest and complete observation digest. [Signed primary geometry and verifier](eight-ms-primary.md) · [Native reward adapter](discovery_margin.py)

The checked native extension uses the original binary64 recurrence, transitions, tie order and stopping conditions. A two-node path receives both node rewards and an extension receives the newly appended node's reward. The experiment changes neither graph edges nor any polynomial, noise, fit or regional gate code. The unit audit checked every chosen path, edge order, lift and objective score exactly against the released native call on both recordings. Unit preparations matched the stock complete Graph fingerprints, and unit saved runs reproduced the raw 8 ms science and all PNG hashes. The saved checks used the installed solver's original NumPy-to-JSON conversion to compare the graph consumed by inference with the graph-only result. [Component tests](../../../tests/pipeline_eval/test_discovery_margin.py) · [Run and audit code](discovery_margin_trial.py) · [Independent scorer](discovery_margin_score.py)

## Accuracy, ownership and cost

| Recording | Reward | Fixed / fitted error (km) | Fixed / fitted RF RMS (Hz) | Prepared points / tracks / curved | Owners per arm |
|---|---|---:|---:|---:|---:|
| North | Unit | 0.682 / 0.158 | 96.75 / 97.68 | 504 / 30 / 15 | 377 |
| North | Weighted | 0.556 / 0.105 | 94.72 / 95.66 | 503 / 30 / 15 | 377 |
| DS30-0016 | Unit | 0.501 / 0.997 | 134.03 / 133.74 | 301 / 12 / 3 | 115 |
| DS30-0016 | Weighted | 0.501 / 0.997 | 134.03 / 133.74 | 315 / 13 / 3 | 115 |

North clears the 250 m comparison against the 12 ms fix in both arms and fails against named v3 in the fixed arm. Weighting the discovery objective moved the North result even though the installed downstream solver assigned the same observations and roles. The physical graph gained a track and 14 prepared points, and the final owners, roles, frequencies and positions stayed exact. Both cases published all expected grids, paths and eight PNGs per run. The earlier history filter changes selected measurements, and its proposed conditional variance change lacked independent calibration data. This intervention keeps the complete measured input and changes the prepared graph. [Archived v3, 12 ms and 8 ms controls](eight-ms-physical.md) · [Earlier continuation study](continuation-quality.md) · [Owner and publication evidence](measurements/discovery-margin.json.gz)

| Recording | Stock / unit / weighted Graph CPU (s) | Unit / weighted numerical CPU (s) | Unit / weighted saved process CPU (s) |
|---|---:|---:|---:|
| North | 0.168 / 0.177 / 0.176 | 3.779 / 3.675 | 7.057 / 6.925 |
| DS30-0016 | 0.063 / 0.068 / 0.070 | 2.702 / 2.619 | 5.728 / 5.628 |

Graph clocks average forward and reverse orders with the same setup, including per-call reward binding. The first unit measurements incurred roughly half a second of asymmetric lazy imports. The receipt retains those runs, and the table uses the prespecified corrected timing repeat with dependencies warm. The saved process clocks include original publication and verification and comprise one pair per recording. They exclude waveform acquisition. [Raw clocks, warm graph repeat and stage counts](measurements/discovery-margin.json.gz)

Run `discovery_margin_trial.py build BUILD_DIR`, `graph CASE BUILD_DIR GRAPH_JSON`, `graph CASE BUILD_DIR SHAPE_JSON --shape-only`, and `replay CASE BUILD_DIR GEOGRAPHIC_SO GRAPH_JSON OUTPUT`. Use `--regional REGIONAL_SO` for the original North route. Use the same installed payload, archive-readable account, shared Gauss CPU 2 lock, one numerical thread, `nice -n15` and `ionice -c2 -n7` as the original 8 ms trial. For `discovery_margin_score.py OUTPUT GRAPH_JSON SHAPE_JSON SCORE_JSON`, put the checkout and its `src` ahead of the installed payload. Thirteen focused and adjacent tests passed. [Recorded build and commands](measurements/discovery-margin.json.gz) · [Tests](../../../tests/pipeline_eval/test_discovery_margin.py)
