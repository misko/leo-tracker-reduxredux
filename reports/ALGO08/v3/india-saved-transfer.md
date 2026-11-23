# Full-catalogue solver replay on the public India waveform packet

On the previously published India containing offer, the full-catalogue research route reduced the saved solve from **5.872 to 3.938 seconds elapsed**. Horizontal errors rose by **18 m** with `c = 0` and **15 m** with fitted `c`. On the existing offer that omits the receiver by 1.5 km, both stock and full-catalogue routes returned false fixes. Their original regional checks reached the same `inside_score` outcome. Both calibration arms preserved all 517 satellite assignments and roles on both offers. [Frozen protocol](india-saved-transfer-protocol.md) · [Scored comparison](measurements/india-saved-transfer-summary.json) · [Full receipts](measurements/india-saved-transfer.json.gz)

## Original detector and visible offers

This development input comes from synthesized dual-receiver Qin CI16 processed by the earlier native wide GLRT. The released schema-v1 document supplies all 2,400 probe rows, fractional candidates, original ADC counters, UTC anchor and 1,200 delivery-clock records required by the v3 numerical solver. Its decoded bytes match the published detector lock and the previously scored comparison. All 35 TLE collection receipts and 23 distinct payloads match the original strictly causal archive. Both runs use the same locked TrackConfig. No raw waveform or untouched evaluation data entered this replay. [Earlier waveform comparison and detector provenance](../single-core-2x/covariance-geographic-transfer.md)

| Previously published 25 km square | Offer center | Reference clearance from nearest face | Center-only error |
|---|---|---:|---:|
| `0000d0a5cbc2b3f00f7b0a49e0b9750c`, containing | 10.096731675° N, 76.901883621° E | +3.576 km | 8.939 km |
| `67f59d17b7ae5f7872896ce04a66d1c9`, omitted | 10.050997700° N, 76.901883621° E | −1.500 km | 14.025 km |

Both offers and their simulated reference were disclosed in the original waveform and covariance reports. Both offer centers use the reference longitude. This replay reused those exact original offers and the same input for both routes. The scorer opened the locked public coordinates after all four runs had sealed their predictions and files. [Development protocol and geography](../single-core-2x/PROTOCOL.md) · [Input pins and final scores](measurements/india-saved-transfer-summary.json)

## Geography, RF and runtime

| Offer and route | Horizontal error, `c = 0` / fitted (km) | RF RMS, `c = 0` / fitted (Hz) | Geographic outcome | Solve elapsed (s) | Solve through plot writes, elapsed (s) |
|---|---:|---:|---|---:|---:|
| Containing, installed v3 | 1.017 / 0.751 | 15.536 / 15.306 | Correct fix | 5.872 | 7.838 |
| Containing, full catalogue | 1.035 / 0.766 | 15.539 / 15.307 | Correct fix | 3.938 | 5.825 |
| Omitted, installed v3 | 1.580 / 1.534 | 15.631 / 15.451 | False fix | 6.033 | 7.960 |
| Omitted, full catalogue | 1.586 / 1.538 | 15.631 / 15.451 | False fix | 5.753 | 7.655 |

Installed v3 reproduced the earlier installed-v2 and covariance endpoints, RF RMS, owner hashes and decisions. The candidate's warm signed pair passed directly on both offers. On the containing offer the endpoints stayed in the interior, so the released exterior check skipped probing in both routes. On the omitted offer both arms reached the north face. Each guard stopped after 26 probes, when an interior receiver score met or exceeded a best eligible far-exterior score. This veto requires exterior clearance of at least one square width. Its result leaves the original near-boundary false fix in place. [Exterior evidence and arm scores](measurements/india-saved-transfer-summary.json) · [Earlier region behavior](../single-core-2x/covariance-geographic-transfer.md)

The omitted guard took **0.311 CPU seconds** in stock and **1.901** in the research route for the same terminal evidence. Stock reuses the causal catalogue bound during preparation, while the research route requests a separate causal catalogue from the same archive. Solve CPU was **5.871 → 3.938 s** containing and **6.032 → 5.746 s** omitted. Through plotting and writes, CPU was **7.837 → 5.824 s** and **7.960 → 7.638 s**. The omitted run paid for the entire original guard call. Neither candidate used the installed inference fallback. [Measured checks and clocks](measurements/india-saved-transfer.json.gz)

## Numerical evidence and renderer boundary

Both routes produced complete matched-arm numerical grids and position paths, with **179** grid points on the containing offer and **137** on the omitted offer. Objective replay differed by exactly zero within every fit. Each standard-renderer output contains eight PNGs, and the audit decoded all 32 files and hashed their original bytes and RGBA pixels. Across routes, the numerical path, grid and rendered file hashes differed on both offers. [Numerical evidence digests](measurements/india-saved-transfer.json.gz)

The saved wide-GLRT packet predates the raw-bound v3 publication path. Its source lacks `input_manifest_sha256`, `analysis_manifest_sha256` and `raw_recording_authority_digest`, and it carries the older wide-GLRT detector signature. The unchanged packet entered `algo08_position.solve` and the pinned release's original standard renderer. The plot and numerical files are genuine research outputs. Their measured clock begins at the solver boundary and excludes raw acquisition, recording verification, the official web store and the independent PNG decoding pass. [Saved-input runner](india_saved_transfer.py) · [Original v3 saved-input checks](joint_publication.py)

## Reproduce

The default staged input is `/tmp/leo-algo08v2-2x-bench/portable-v5-geodiverse/02213f589249d02be64805a5d2ea12ef`. Use fresh outputs named `matched-tile-stock`, `matched-tile-full-catalogue`, `omitted-tile-full-catalogue` and `omitted-tile-stock` in that order. Once all four receipts exist, run `score DIR SUMMARY FULL` with the checkout's `reports/ALGO08/v3`, repository root and `src` on `PYTHONPATH` and the same scheduling limits. Forty focused tests passed. [Protocol](india-saved-transfer-protocol.md) · [Component tests](../../../tests/pipeline_eval/test_india_saved_transfer.py)

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
lock=/tmp/leo-algo08v2-2x-bench/gauss.lock
flock -x "$lock" ionice -c2 -n7 nice -n15 taskset -c 2 timeout 110s \
  env PYTHONPATH="$PWD/reports/ALGO08/v3:$payload:$release/src:$release:$PWD" \
  OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  "$release/venv/bin/python" -BPs reports/ALGO08/v3/india_saved_transfer.py \
  run "$mode" "$route" "$output"
```
