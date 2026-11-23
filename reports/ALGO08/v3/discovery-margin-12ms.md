# Continuous discovery reward on sealed 12 ms detections

The frozen reward gave North exactly the same fix in both calibration arms. Its fixed arm remained **284 m farther from the reference than named ALGO08v3**, exceeding the 250 m allowance by **34 m**. DS30-0016 improved by **510 m fixed and 769 m fitted** over its genuine 12 ms control. Both cases returned complete publications. The joint development gate stopped the trial before South and DS30-0057. [Frozen protocol](discovery-margin-12ms-protocol.md) · [Scored evidence](measurements/discovery-margin-12ms.json.gz)

The original 20 ms stereo anchors occupied slot zero of every eight admitted visits per RF, channel and edge. The original 12 ms primary archived its independently rolled control, signed fractional exact score, CFO and full selected-factor order. The audit verified every stored `exact - control` margin against the original arithmetic and qualification. North had 1,200 admitted visits, with 82 selected anchors and 996 selected nonanchors. DS30-0016 had 713 admitted visits from 808 issued, with 74 anchors and 401 nonanchors selected. All factors entered Graph in both modes. Anchors received unit weight and nonanchors used `clamp(1 - 0.025 / margin, 0, 1)`. The receiver threshold is the same as in the earlier 8 ms experiment. The continuous weight is a heuristic for discovery, and measurement errors, noise weights and physical objectives used their original calculation. [Original receiver and cases](eight-ms-physical.md) · [Earlier 8 ms result](discovery-margin.md) · [Native reward and binding](discovery_margin.py)

| Recording | Reward | Fixed / fitted position error (km) | Fixed / fitted RF RMS (Hz) | Graph points / tracks / curved | Owners per arm |
|---|---|---:|---:|---:|---:|
| North | Named v3 | 0.106 / 0.141 | 5.406 / 5.167 | | |
| North | Unit | 0.390 / 0.121 | 69.401 / 70.860 | 485 / 32 / 13 | 347 |
| North | Weighted | 0.390 / 0.121 | 69.401 / 70.860 | 485 / 32 / 13 | 347 |
| DS30-0016 | Named v3 | 1.644 / 1.661 | 109.375 / 109.479 | | |
| DS30-0016 | Unit | 1.311 / 1.694 | 121.526 / 120.291 | 354 / 13 / 3 | 116 |
| DS30-0016 | Weighted | 0.801 / 0.925 | 121.457 / 120.844 | 370 / 14 / 4 | 125 |

The complete North Graph and science fingerprints, all owner identities and roles, and all rendered images matched with either discovery reward. The North archive had confirmed nonanchor weights as low as 0.00232 and all 40 native path calls executed, so the unchanged result came from the same prepared Graph winning with the new rewards. For DS30-0016 both arms kept all 116 existing owner identities and roles and gained nine predictive owners. Fixed-arm RF RMS fell by 0.070 Hz and fitted-arm RF RMS rose by 0.553 Hz while both physical position errors fell. [Coordinates, owner changes and per-arm differences](measurements/discovery-margin-12ms.json.gz)

The independent readback verified the complete 137-point North and 179-point DS30-0016 grids, position paths, and all eight PNGs in each of the four saved runs. Unit rewards matched archived original terminal, science, owners and PNG hashes. The raw and saved grid documents differed only in recorded elapsed seconds and the resulting document digest. North's supplied offer contained the reference with 0.100 km clearance and both modes kept the original `inside_score` decision after 25 exterior probes. The physical offer clearance was 6.179 km. Each mode reached `eligible_exterior_separation` at 24 probes with no withhold. The physical route used the original geographic projector and configuration. [Checked regions, probe outcomes and media evidence](measurements/discovery-margin-12ms.json.gz)

| Recording | Stock / unit / weighted Graph CPU (s) | Unit / weighted numerical CPU (s) | Unit / weighted saved process CPU (s) | Unit / weighted saved process elapsed (s) |
|---|---:|---:|---:|---:|
| North | 0.1645 / 0.1686 / 0.1686 | 3.616 / 3.795 | 6.858 / 7.098 | 6.860 / 7.100 |
| DS30-0016 | 0.0718 / 0.0752 / 0.0764 | 2.516 / 2.746 | 5.432 / 5.718 | 5.434 / 5.720 |

Graph CPU averages two warm runs per mode with reward binding included. Exact parity checks verified each unit native path against the installed recurrence, with 40 North paths and 29 physical paths. Weighted Graph cost 4.07 ms more than stock on North and 4.55 ms more on DS30-0016. The complete saved timings include inference, publication and verification. They are single ordered pairs and include execution variability, including on North where the complete Graph stayed identical. No waveform payloads were read and these timings exclude waveform acquisition. [Machine, clocks, pins and commands](measurements/discovery-margin-12ms.json.gz)

Use the earlier native build and launch steps with `--aperture 12ms` for `graph` and `replay`, supplying the recorded North regional library and the shared geographic library. The graph readback supplies both graph and solver-shape arguments to `discovery_margin_score.py`. Runs used one numerical thread under the shared Gauss CPU 2 lock with `nice -n15` and `ionice -c2 -n7`. Fourteen focused and adjacent component tests passed. [Run adapter](discovery_margin_trial.py) · [Scorer](discovery_margin_score.py) · [Tests](../../../tests/pipeline_eval/test_discovery_margin.py)
