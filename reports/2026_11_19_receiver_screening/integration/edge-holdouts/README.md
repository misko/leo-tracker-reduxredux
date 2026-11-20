# Frozen compact edge rule across three new latitudes

The frozen compact receiver stopped all six omitted-tile publications in each calibration arm. It preserved all three containing-center fixes and two of the three near-inside fixes, with unchanged coordinates and RF on every accepted offer. The valid tile with the site only **0.593 km inside** lost both publications because the fitted-`c` endpoint reached a face. The `c = 0` endpoint on that same tile remained 0.587 km inside the compact coordinates. [Sealed scores](scores.json) · [Prediction seal](prediction-lock.json)

## Independent sites and controls

New sequestered seeds drew three separate simulated receivers at 58.21°N, 3.74°S and 44.63°S, with different causal TLE payloads. The sites were at least 1,995 km from the bound earlier locations. Each site contributes one 300 s factor stream and four offers on that same stream. The causal archive and disturbance windows come from recorded histories. The receiver used authentic earlier TLEs and the original Graph and compact v5 fit. The controller generated the GLRT time, folded CFO and frame-epoch factors, with measured donor residual and visit-gap replay. The workers received only the allowed causal history, factor document and opaque tile. The released seed and coordinates were committed separately before inference. [Protocol](PROTOCOL.md) · [Input lock](input-lock.json) · [Causal histories](causal-history.json) · [Released targets](released-labels.json)

The frozen policy requires strict majority compatibility before conservative recovery and stops that stage at 55 s. Full fits then require both calibration endpoints to be more than 20 m inside the compact tile. All three far stock controls ran independently through complete compact secant on identical requests. For the other nine queries, the controls are the exact same scientific endpoints before the terminal decision. Their stock timings are unmeasured. Any early stop without a matched full worker would have no stock endpoint. [Source lock](source-lock.json) · [Prediction data](predictions.json) · [Matched chart records](chart-positions.jsonl.gz)

## Position and tile decisions

Values paired within cells follow `c = 0` / fitted `c`. The signed margins are physical distances to the true site's nearest tile edge. Each row is one independent simulated location. Published and forced errors are in kilometres.

| Site | Center published error | True near-edge margin | Near-inside decision | Near-outside forced error | True far margin | Independent stock far error |
|---|---:|---:|---|---:|---:|---:|
| 58.21°N | 0.316 / 1.499 | ±0.593 km | Withheld, forced 0.319 / 1.272 | 0.792 / 0.688 | −57.620 km | 69.379 / 68.052 |
| 3.74°S | 1.114 / 1.030 | ±1.158 km | Published, 1.111 / 1.024 | 1.416 / 1.399 | −36.854 km | 36.872 / 36.872 |
| 44.63°S | 3.444 / 3.223 | ±2.457 km | Published, 3.444 / 3.223 | 3.884 / 3.708 | −58.232 km | 92.332 / 92.996 |

All three near-outside fits reached the compact face in both arms and were withheld there. The strict compatibility rule rejected all three far offers before recovery with 35.3%–43.7% of nominated observations compatible. Those candidate rows have no forced estimate. The independently computed stock far controls published on all three offers in both arms. The table separates those false publications from diagnostics at the terminal face. [Zero-calibration figures](figures/c0/transfer.pdf) · [Fitted-calibration figures](figures/fitted_c/transfer.pdf)

## Frequency fit and runtime

The full-fit containing RF RMS pairs were 69.091/69.157, 71.977/71.970 and 56.554/56.562 Hz. The respective near-outside forced fits were 69.085/69.150, 71.978/71.973 and 56.716/56.723 Hz. These small RF differences accompanied materially different boundary decisions. The far controls also produced RF RMS between 63.71 and 71.29 Hz while publishing errors of 36.87–93.00 km. [RF and geometric distributions](scores.json)

All 15 requested workers finished in a 164.35 s envelope on four single-threaded low-priority cores. The three far candidate stops took 24.06–31.58 s and their full controls took 47.55–61.13 s. The remaining guarded completions took 21.90–49.02 s. No request reached the 115 s outer deadline or the 55 s internal recovery deadline. The three near margins differ at three different sites. Their observed coverage does not isolate a universal cutoff in true distance to the edge. [Earlier independent edge pair](../../deployment/transfer-budget/interior-guard/README.md)
