# Original v5 numerical reference on an offered region

The private harness invokes the frozen `v5_lean` numerical worker and its established endpoint renderer. It uses the original no-repair v5 option, including the original collection, association, recovery, admission, and final selection stages. Both calibration arms use the same worker call. The harness exists for comparison against compact receivers on relocated inputs. [Protocol](PROTOCOL.md) · [Private entry](../../../../tools/pipeline_eval/qualification/v5_regional_reference.py)

## Geography and authority audit

| Boundary | Geographic input and handling |
|---|---|
| Public evaluation dispatch | `v5_lean.run_bound_worker` allows the authenticated roof panel and one original 25 km offer. The private research controller invokes its existing numerical worker directly. |
| Frozen job validator | The published request contract requires `[37.906, −122.545]` to protect the production figure frame. The private validator supplies that frame to the original validator on a shallow copy, then returns the actual offered coordinates to the worker. Every other field passes the original validation. |
| Orbit screen and numerical search | `prepare_initial_sky` receives the explicit broad screen and constructs the causal orbit bank about it. `SearchRegion` receives the actual offered center and its original default 25 km width. The local longitude transform depends on latitude, so the private controller requires the tile to stay clear of poles and the longitude seam. |
| Final rendering | The frozen engine has a second literal roof check inside `render_inference`, after `infer_prepared` completes. The established numerical-only `v5_lean` endpoint renderer already extracts both selected estimates at that boundary. |
| Ground truth and orbit labels | The job has a null evaluation reference and one opaque scan identity. The isolated worker sees authenticated staged native factors, configuration, past-only TLE files and the offer. The entire simulation controller directory is masked in the worker. Geographic truth and emitting-orbit labels stay with the independent scorer. |

The frozen worker checks the original source and original runner hashes, native input and track configuration SHA-256, numerical runtime versions, and catalogue archive membership and bytes. The relocated job changes the offered centers, opaque identifiers, and scientific input bindings to the new packet. Its model, role, policy, native backend and calibration arms are inherited from the authenticated original no-repair request. [Public v5 worker](../../../../tools/pipeline_eval/variants/v5_lean.py) · [Blind input binding](../../../../tools/pipeline_eval/qualification/v5_regional_blind.py)

## Authentic roof transport

The first DS29-0082 run used the original archive input paths and reached the late admission stage at the 240-second deadline. The service used 153.2 CPU seconds and peaked at 1.38 GiB. The completed stage and timing receipts are preserved. The per-field parity comparison has no available endpoint for that invocation. [First prediction](roof-prediction.json) · [First prediction seal](roof-prediction-lock.json)

The matched roof retry used a 330-second cap and byte-checked copies of the original native input, configuration and complete causal archive on local ext4. The numerical worker and request options use the same source and numerical policy as the first attempt. [Retry plan](roof-retry/plan.json)

The retry finished in **217.65 s wall and 154.57 s process-group CPU**, with 1.37 GiB peak memory. Both coordinates, both conditional RF RMS values, both frequency scores, and every compared counter match the archived original numerical replay exactly. Both arms use 929 associated observations. The original prepared scan has 1,868 observations and 61 tracks. All 18 original stage names occur in the same order through final selection. [Measured retry](roof-retry/prediction.json) · [Exact comparison](roof-retry/parity.json) · [Retry prediction seal](roof-retry/prediction-lock.json)

## Matched blind inputs

The predeclared ordering selects opaque session `c00e499607481527b446a4a4e3ac0e15`. Its two offers begin `7ada2d17` and `7e833adf`. Both worker jobs use the same 13,636 native probes, clock bracket, exact native and configuration hashes, and all 35 strictly prior TLE snapshots. The newest received payload equals the sealed compact-study catalogue. Each worker stages only those authenticated scientific inputs and receives its own explicit screen and 25 km tile. The two offer labels stayed with the independent controller until terminal predictions sealed. [Blind request and original worker options](blind-plan.json) · [Causal snapshot digests](causal-snapshots.json)

## New simulated location

The independent scorer identified `7e833adf` as the containing offer and `7ada2d17` as the near-omitted offer. All two-value cells give `c = 0` followed by fitted `c`. The original numerical route processed both arms on the same request. [Terminal prediction seal](prediction-lock.json) · [Matched score ledger](../compact-blind/scores.csv) · [Score and truth-release seal](../compact-blind/score-lock.json)

| Offer and receiver | Horizontal error, km | Conditional RF RMS, Hz | Factor-to-position wall |
|---|---:|---:|---:|
| Containing, original v5 numerical | 1.772821 / 1.371942 | 38.840383 / 38.792337 | 161.68 s |
| Containing, installed phase release | 1.773910 / 1.364361 | 38.840371 / 38.792408 | 79.49 s |
| Near omitted, original v5 numerical | Deadline | Unmeasured | 240.28 s |
| Near omitted, installed phase release | 1.767555 / 1.638931 | 38.976658 / 38.941943 | 47.57 s |

The containing original completed all 18 stages, using 3,031 winning observations, 24 tracks and 2,689 associated observations in each arm. It used 155.81 CPU seconds and peaked at 1.55 GiB. The original near-omitted run completed the family stage and reached its service deadline after 235.45 CPU seconds. Its geographic decision remains unresolved. The installed phase release issued a fix in both arms on that omitted offer. [Per-case predictions and stage receipts](predictions.jsonl.gz)

The original and installed containing fits use one simulated location. The two offers measure geographic accuracy and omitted-offer behavior separately. The archived roof result establishes same-request numerical parity for the private entry. [Zero-c comparison](../compact-blind/charts/c0/compact-blind-original-numerical-reference.png) · [Fitted-c comparison](../compact-blind/charts/fitted_c/compact-blind-original-numerical-reference.png) · [Chart seal](../compact-blind/reference-figure-lock.json)

```sh
.venv/bin/pytest -q tests/pipeline_eval/test_v5_regional_reference.py
```
