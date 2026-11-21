# ALGO08 with an explicit search region

ALGO08 takes a regional prior from the operator. On two blind simulated raw recordings the fitted position errors were 0.71 km and 1.11 km when the search square contained the receiver. It also published four fixes from four squares that excluded the receiver. All four landed on the boundary. The supplied region is a scientific input, and an accepted local fix does not establish that the region is correct.

## What changed

The [audit of the earlier release](../location-audit/README.md) traced two fixed coordinates to the orbital screen and position prior, and reproduced a map-publication failure when the position frame moved.

The station file supplies a square center and full side length. The sky builder uses the same center unless the station specifies a separate screening center. The position search, both calibration fits, objective grid, optimizer path, terminal receipt, eight PNGs and web result use this configuration. Moving the square, changing its width, or moving the screening center produces a distinct localization run. Site-independent two-scan detections can be reused. An optional reference creates a separately identified annotated publication and enters only after fitting. The historical Gauss profile preserves both of DS30's original centers. Previously published ALGO07 and ALGO08 results retain their original contracts. [Station profile](../../../deploy/gauss/algo08-region.json) · [Run instructions](../README.md)

## Full DS30 compatibility

The regional release reproduced **all 455 recording decisions** on Gauss with the historical station profile. It returned 439 fixes, withheld on 15 recordings and reproduced the existing solver failure on the incomplete DS30-0340 capture. Each returned latitude, longitude and solver frequency RMS matched exactly in both calibration arms. Scoring the locked positions against DS30's original per-recording reference authority also reproduced every original horizontal error. [All 910 arm comparisons](ds30-replay.csv) · [Frozen DS30 benchmark](../../2026_11_21_ds30_full/README.md)

| Arm | Fixes / assigned | Median error | 90th percentile | 95th percentile | Within 1 km / assigned | Median solver frequency RMS |
|---|---:|---:|---:|---:|---:|---:|
| Fitted RF calibration | 439 / 455 | 0.814 km | 1.873 km | 2.258 km | 274 / 455 | 115.05 Hz |
| Fixed zero | 439 / 455 | 0.828 km | 1.856 km | 2.299 km | 266 / 455 | 115.08 Hz |

Percentiles use returned positions. The full cohort replay started from the original digest-verified two-scan detections and rebuilt tracks, causal sky, associations, both positions and their regional presentation evidence. All 439 successful runs returned a grid and path in the requested frame. The independent sealed-I/Q and PNG checks below cover acquisition and publication. The Gauss web annotation uses a station reference approximately 0.75 m from the DS30 scoring reference, which accounts for submeter differences in the web error label.

## Blind raw-I/Q transfer

Two fresh simulated stationary sites were drawn independently of DS30, one in central Europe and one in southern Africa. Each recording contained 1,200 native 20 ms dual-receiver CI16 windows at 10 MS/s over five minutes on eight channels. The generator used a lower-edge schedule for the northern site and an upper-edge schedule for the southern site. It synthesized pilot timing and Doppler from later orbital elements, along with noise, a tone, echoes, receiver offsets and drift. The inference account could read the sealed recordings, unlabeled regional offers and causal TLEs. Its filesystem permissions excluded the scoring key. Both sites and all six offers used the same detector, solver and acceptance settings.

| Simulated recording | Offered 25 km square | Center error | Fitted position error | Fixed-zero error | Frequency RMS, fitted / zero |
|---|---|---:|---:|---:|---:|
| North | Contains receiver | 6.70 km | 0.71 km | 0.74 km | 5.17 / 5.38 Hz |
| South | Contains receiver | 6.60 km | 1.11 km | 0.83 km | 6.39 / 6.50 Hz |
| North | Receiver 1.5 km beyond edge | 13.98 km | 1.51 km | 1.54 km | 5.20 / 5.54 Hz |
| South | Receiver 1.5 km beyond edge | 13.98 km | 2.57 km | 2.39 km | 6.53 / 6.64 Hz |
| North | Receiver 52.5 km beyond edge | 64.93 km | 52.49 km | 52.46 km | 37.53 / 37.95 Hz |
| South | Receiver 52.5 km beyond edge | 64.93 km | 53.58 km | 53.58 km | 6.47 / 6.47 Hz |

The acceptance rule returned a position in every row. Changing only the offer on the southern recording increased fitted error from 1.11 km to 53.58 km, while its frequency RMS changed by just 0.08 Hz. A boundary hit identified these four false publications after scoring. The original 439 DS30 fitted and fixed-zero fixes all lay more than 100 m from their box edge. These counts describe this panel and this roof. A boundary-based withholding rule would need an independent test that includes valid sites close to a box edge.

All six runs published eight digest-verified, decoded PNGs. The maps below are the original estimator outputs from before the predictions were joined to the scoring key. The receiver had no evaluation marker. [Scored offers](blind-scores.csv) · [Locked predictions](predictions.json) · [Revealed scoring key](scoring-key.json)

| Supplied square | Northern site | Southern site |
|---|---|---|
| Contains receiver | [Position PNG](north-containing.png) | [Position PNG](south-containing.png) |
| Near miss | [Position PNG](north-omitted.png) | [Position PNG](south-omitted.png) |
| Far miss | [Position PNG](north-far.png) | [Position PNG](south-far.png) |

## Measured Gauss recording from raw samples

DS30-0003 supplied 6,769 raw visits, of which 6,714 passed capture checks. Its station profile reproduced the frozen fitted and fixed-zero coordinates and solver RMS exactly. Two further runs shared the same detections, changed the search and sky screen together, and had no evaluation reference until scoring. All three published valid path/grid sidecars and eight decodable PNGs apiece. The 40 km run exercises the renderer at a different width. [Recording-level publications and verification](gauss-raw.json) · [40 km position PNG](gauss-40km.png)

| Offer | Width | Fitted error | Fixed-zero error |
|---|---:|---:|---:|
| Historical station profile | 25 km | 375 m | 373 m |
| Translated square containing the roof | 40 km | 1,006 m | 900 m |
| Square north of the roof | 25 km | 61.20 km | 61.15 km |

Gauss also ran DS30-0003 through the packaged station launcher. The live API served the version 3 manifest, the grid and path in the declared frame and all eight original PNGs. Each image decoded and matched its published byte count and SHA-256. Historical ALGO07 version 1 and ALGO08 version 2 manifests remained readable. [Web verification](gauss-http.json) · [Gauss LAN result](http://gauss:8090/api/v2/fast-scans/algo08-8d0be51af6a22162c365fc5a778f4485/standard-analysis)

The center controls the search origin and the width controls its full side length. This evaluation exercised 25 km and 40 km squares. Wider-area sky coverage, pole crossings and longitude wrap were outside the experiment.

The automatic watcher switched to release `081ab0265` between child runs. It then completed the November 21 14:59 UTC upper-edge recording using the station profile. On the normal scan page, Chromium displayed the regional prior, decoded all eight figures and fetched each image by its verified digest. [Automatic scan on Gauss](http://gauss:8090/?scan_kind=fast&scan_id=fast8-auto-20261121-145902-25fac6de-1-upper) · [Browser verification](automatic-web.json)

## Runtime check

Timing began with decoded two-scan detections in memory. Each paired trial used the same CPU, a single numerical thread, identical source detections and identical orbit inputs. The fit includes the conditional diagnostic grid. All four fits evaluated the same 179 grid locations. The two paired trials reverse execution order. The original and regional installations had byte-identical detector, pilot, projector and native position kernel assets. [Timing harness](timing.py) · [Per-run CPU and elapsed measurements](timing.csv)

| Recording | Fit CPU, original → regional | Figure CPU, original → regional | Fit and figures elapsed, original → regional |
|---|---:|---:|---:|
| DS30-0003 | 80.5 → 81.7 s | 8.5 → 8.4 s | 91.4 → 94.9 s |
| DS30-0012 | 126.8 → 128.1 s | 7.8 → 7.5 s | 140.5 → 137.7 s |

The table uses the matched pass with per-process transparent huge pages disabled on both installations. The initial pass encountered host paging and showed substantial elapsed-time variation. Both passes are in the CSV. Two recordings support a timing spot check only. No raw acquisition or embedded-device timing was measured in these pairs.

## Independent physical stations

The compatible full-pipeline field evidence in this evaluation comes from Gauss. The StarLoc archive supplies selected single-channel tone tracks, the Watson archive supplies power spectra, and the Austin waveform excerpt supports short pilot timing checks. None supplies a compatible off-site sealed dual-receiver scan with the time/channel coverage used here. The two simulated sites test the complete software path and its response to a wrong prior. Physical relocation accuracy and false-publication rates remain unmeasured. [StarLoc measurement boundary](../../2026_11_18_blind_regional_receiver/README.md) · [Austin waveform excerpt](../../2026_11_19_receiver_screening/arrival-and-timing/austin-waveform/README.md) · [Watson spectra](../../2026_11_19_receiver_screening/receiver-deadline/external-spectrum/README.md)

## Reproduction

Use the release's numerical environment and qualified native assets. From a source checkout, rebuild the native bound manifest at its actual location using the release staging script. Its source and wrapper paths are checked at startup. Set `ALGO08_ASSETS` to the corresponding asset directory for the DS30 replay.

1. Run [ds30.py](ds30.py) with no arguments to authenticate the DS30 prediction lock and verify historical search/screen bindings. Pass a recording ID to rerun positioning on its original, digest-checked two-scan detections and capture-era orbit archive. Save its JSON as `DS30-NNNN.json` for IDs 0001 through 0455. Invoke [summarize_ds30.py](summarize_ds30.py) with that directory and a report directory to verify all 910 arm rows against the frozen decisions, coordinates, frequency RMS and scoring references.
2. Make a fresh workspace with a world-traversable root, a public input directory, a `scorer` directory private to the generating account and an output directory writable by a separate inference account. Run [blind_panel.py](blind_panel.py) with the workspace path. It generates both raw recordings and commits the private key digest in the public panel. After unblinding, `--replay-seed` accepts the hex seed in the scoring key to regenerate the same radio samples. A newly sealed manifest has fresh creation timestamps.
3. Under the inference account, run [run_panel.py](run_panel.py) with the public directory, output directory (`outputs/blind`) and release assets. It executes the normal ALGO08 CLI without a reference, checks grids and paths, decodes every published PNG and emits the SHA-256 of the locked predictions.
4. Under the scoring account run [score_panel.py](score_panel.py) with the workspace, the independently recorded prediction digest and the report directory. It verifies the commitment, checks each inclusion label geometrically and joins truth only for scoring. The prediction digest for this panel is `46e8925aad5b047b89f57b95d22581a5eca4dfc52f3196790154c01bdc340549`.
