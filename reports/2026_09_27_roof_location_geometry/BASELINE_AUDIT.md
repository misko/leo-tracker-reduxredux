# Frozen roof-holdout location baseline audit

Read-only audit of the installed `scanner-adaptive-tle-position-v2` products and search implementation for the four frozen holdouts. No search was started.

## Installed search contract

The two branches are generated independently:

| Branch | Center | Radius |
|---|---|---:|
| Sacramento | 38.5816, -121.4944 | 250 km |
| Reno | 39.5296, -119.8138 | 500 km |

The installed configuration requires tracks spanning at least 3 seconds with at least 6 observations, uses the fixed `cf510316-fixed-partition-v1` partition, and evaluates TLE timing offsets `-5..+5 s`. `adaptive_best_first_search` uses a 1,000 km region, nominal levels 100, 50, 25, and 12.5 km, and a 400-point budget. The persisted searches below all stopped at that point budget and are explicitly incomplete.

The published objective is `duration-weighted-capped-rmse-800hz-v1`; published identity selection is `randomized-evaluation-rms-v1`. Thus the published result is a diagnostic baseline, not a clean held-out geometry comparison: evaluation residuals participate in identity selection.

## Published holdout baselines

`scan-fw-00ff81dc09fc738a` is currently `pending` in `AdaptiveTlePositionStoreV2`; it has no published position manifest. It must remain missing rather than be reconstructed from partial files.

| Session | Branch | Selected latitude, longitude | Error to diagnostic reference | Capped RMS | Tracks | Observations |
|---|---|---|---:|---:|---:|---:|
| `898b709…` | Sacramento | 37.847242, -122.419735 | 5,791 m | 200.60 Hz | 58 | 2,166 |
| `898b709…` | Reno | 37.869502, -122.448263 | **3,994 m** | 201.39 Hz | 58 | 2,202 |
| `3ebf352…` | Sacramento | 37.847242, -122.419735 | 5,791 m | 238.96 Hz | 63 | 1,799 |
| `3ebf352…` | Reno | 37.869502, -122.448263 | **3,994 m** | 233.76 Hz | 63 | 1,806 |
| `851486c…` | Sacramento | 37.846029, -122.562082 | 6,719 m | **114.92 Hz** | 62 | 2,039 |
| `851486c…` | Reno | 37.869502, -122.448263 | **3,994 m** | 117.51 Hz | 62 | 2,065 |

All three products evaluated 400 points per branch at a finest 12.5 km spacing. The selected and finest incumbents coincide. The bold RMS indicates the lower published objective within a scan; bold error indicates the closer branch result. This illustrates why candidate-position ranking and geographic error are distinct outcomes.

Document digests are:

- `898b709…`: `sha256:47869c99cfa34bef12c64e929c61daa13df436e3478a898753b76b36fab65735`
- `3ebf352…`: `sha256:8323fa7b8f0abee6661d3e4d0586c052c67de3753a161282365a8b5816bc1fde`
- `851486c…`: `sha256:11b30e7a97a5853d1e42d529d63d7dc5b730491d8925c93b2e92a17c589ff314`

## Public rerun path for a geometry objective

The bounded end-to-end rerun should reuse these installed public interfaces:

1. `ScannerTrackingInputStore.load(session_id)` obtains the complete, digest-bound tracking input.
2. `prepare_adaptive_tle_position_inputs(..., TleArchiveReader)` reconstructs the 3-second/6-observation tracks, frozen partition, and causal TLE catalogue.
3. `build_prediction_banks(catalogue, candidate_indices, start_utc_ns, tracks)` creates the full-catalogue Doppler prediction banks.
4. Instantiate a separate `RegionalTrackPredictionEvaluator` for each Sacramento and Reno center. Do not union candidates or associations between branches.
5. Use `adaptive_best_first_search(point_evaluator, radius_km=branch_radius, region_size_km=1000)` with the same 400-point/12.5-km configuration for both Doppler-only and geometry-augmented arms.
6. Fit satellite/timing association and all geometry coefficients from each branch's training observations only. Freeze them before held-out scoring. Reception must not choose candidate IDs.
7. Compare the two objectives on identical evaluated coordinates, or rerun the same independent search for each arm. Score the operator-supplied roof coordinate only afterward; it is diagnostic and must not seed candidates, tune bounds, or select a mapping.

The installed orchestration entry point is `leo.cli.adaptive_tle_position.run_adaptive_tle_position`; its persisted output is read through `AdaptiveTlePositionStoreV2.status`. For a new research objective, reuse the public preparation, prediction, evaluator, and search functions rather than modifying or writing the production store.

## Required comparison

For each of four holdouts, report Doppler-only versus Doppler-plus-RX-geometry selected coordinate, branch, error, objective delta, search boundary status, and receiver-mapping reversal. `00ff81…` still has valid cached public tracks for a research rerun even though it lacks a published production baseline; label that baseline unavailable. Four scans permit a bounded holdout result, not a calibrated population accuracy claim.
