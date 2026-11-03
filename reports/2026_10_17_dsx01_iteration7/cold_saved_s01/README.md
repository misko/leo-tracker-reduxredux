# Saved S01 cold endpoint on the original DSX01 cohorts

The saved fresh Space-Track cold endpoint assigns 2,150/4,797 original S01 observations, versus 1,643 for the original endpoint. Its improvement in the three frozen requested windows is only 14 → 17/148. Window 003 remains 0/27. This replay therefore does not establish recovery of the requested tracks. Assignments and satellite identities below are model outputs, not emitter truth.

No optimization, RF collection, station-reference read, endpoint selection or position ranking was performed. Both complete endpoints were frozen in [freeze.json](freeze.json) before evaluating the public reconstructed models. Their original fitted positions are disclosed in [results.json](results.json) solely as saved model parameters; no configured station coordinates or distance were read.

## Fixed membership and assignment accounting

Every observation ID, capture time, actual RF, receiver and channel agrees exactly with the original S01 frozen cohort. The three requested denominators remain 86, 35 and 27. Assignment uses the unchanged rule: maximum satellite responsibility strictly greater than the clutter posterior, with the saved learned q, its normalization and the original 125 Hz Gaussian scale.

| Cohort | Denominator | Original → saved assignments | New / lost | Retained | Retained identity changes | Assigned-population RMS, Hz | Same-observation intersection RMS, Hz |
|---|---:|---:|---:|---:|---:|---:|---:|
| Full S01 | 4,797 | 1,643 → 2,150 | 1,361 / 854 | 789 | 772 | 164.87 → 137.87 | 161.35 → 150.31 |
| DSX01-001 | 86 | 13 → 14 | 11 / 10 | 3 | 3 | 176.27 → 165.06 | 136.51 → 220.69 |
| DSX01-002 | 35 | 1 → 3 | 3 / 1 | 0 | 0 | 107.72 → 102.49 | — |
| DSX01-003 | 27 | 0 → 0 | 0 / 0 | 0 | 0 | — | — |
| Requested union | 148 | 14 → 17 | 14 / 11 | 3 | 3 | 172.28 → 155.86 | 136.51 → 220.69 |
| Outside requested | 4,649 | 1,629 → 2,133 | 1,347 / 843 | 786 | 769 | 164.81 → 137.72 | 161.44 → 149.98 |

The assigned-population RMS uses each endpoint's own changing set. The intersection holds observation membership fixed but permits the identity changes explicitly counted above. Only 17 full-recording observations retain both assignment and identity; their RMS is 187.90 → 110.46 Hz. None of the three retained requested observations retains identity. The requested intersection RMS becomes worse despite the count increase.

All scopes and both c policies are retained in [comparisons.csv](comparisons.csv). Every nonzero assigned identity count is in [identity-histograms.csv](identity-histograms.csv); no identities were removed from the histograms. Point arrays and original observation IDs are in [original.npz](original.npz) and [saved_space_track.npz](saved_space_track.npz). The original fitted-c point arrays exactly match the previously sealed original S01 arrays.

![Original fixed cohorts and paired residuals](coverage-and-paired-rms.png)

![All assigned identity counts, fitted c](identity-histograms-fitted-c.png)

## Saved-state differences and provenance

Both terminals bind the same original tracking input, SHA-256 `3a79382102760ac8e13f6d093e5b0be6bd168e68df4cb7f292cbf6fd87ebf612`. Public `SharedFastScanStore.plot_evidence`, input preparation, causal TLE archive access, regional propagation and `shared_orbit_replay.selected_model` reconstruct each exact selected model. No old investigation script was rerun. Saved stage receipt hashes, terminal/input/launch hashes and both complete vector/nuisance arrays are retained in `freeze.json`; causal TLE metadata and selected-source audits are in `results.json`.

| Quantity | Original S01 | Saved fresh cold endpoint |
|---|---:|---:|
| Provider metadata | huggingface | space-track |
| TLE digest | `2439873f2415acb0df93d408560a30cff267a666be312cfaa6a2734bbd8db197` | `c1341ed302fe6301e1dd4515e5bcee227d4c0c7aa975bdf572f8f3cbfd702072` |
| Archive collection UTC ns | 1792166536105889082 | 1792166533595712561 |
| Regional candidates | 987 | 1,035 |
| Selected candidates | 46 | 59 |
| Selected source | A-3 / shared-all-A-3 | A-4 / shared-all-A-4 |
| Strict replay KKT stationarity | 0.00009602 | 0.00010482 |
| Objective J | 60,983.288 | 58,410.385 |
| Likelihood NLL | 60,114.111 | 57,878.529 |
| Common timing, s | −1.594149 | +0.011598 |
| Relative timing RMS, s | 11.106599 | 7.583306 |
| Learned common RF slope c, Hz/GHz | −315.589483 | −355.867200 |
| Sum of learned q | 1.6 | 1.6 |
| Saved historical elapsed, s | 293.516 | 388.468 |
| Saved historical A/B/shared objective calls | 12,056 | 15,599 |

Both causal archives precede capture start by more than 505 seconds. The archived snapshots were collected approximately 2.51 seconds apart. All selected IDs propagate successfully, with no invalid or outside-prior rejection in this replay. The selected banks share 34 IDs; 12 occur only in the original and 25 only in the saved endpoint. Complete lists are retained in `results.json`, including all original winners and both changed banks.

Both historical receipts declare `generic-cold24-shape3-fresh-six-ab-v1`, 26 optimizer calls and six prescreen objective calls. Discovery, shape and bootstrap have their separate stage receipts; the table's objective counts describe the recorded A/B/shared scope, not an invented total for every pipeline stage. Different catalogue contents, candidate banks, discovery/initialization, calibration, timing, q and geography remain confounded. A lower J or more assignments here cannot be attributed to the provider alone or interpreted as improved localization.

[timings.csv](timings.csv) retains common, relative and total timing for every selected recording-satellite pair. The plot compares both complete selected banks and the same 34 shared selected IDs; common timing is shown separately. Timing is unchanged in the c-zeroing diagnostic.

![Saved timing distributions and common timing](timing-histograms.png)

## Deterministic c = 0 diagnostic

For each frozen endpoint, only physical vector coordinate 6 was set to zero. All other physical parameters, nuisance parameters, q, bands, candidates and priors remain unchanged. This is **not a c = 0 refit or a controlled optimization ablation**; no stationarity is claimed for these zeroed states.

| Cohort | Original → saved assignments | New / lost | Assigned-population RMS, Hz | Intersection RMS, Hz |
|---|---:|---:|---:|---:|
| Full S01 | 1,531 → 1,994 | 1,291 / 828 | 183.13 → 202.66 | 183.89 → 194.42 |
| DSX01-001 | 11 → 14 | 11 / 8 | 119.99 → 145.29 | 113.81 → 184.55 |
| DSX01-002 | 1 → 3 | 3 / 1 | 89.52 → 265.17 | — |
| DSX01-003 | 0 → 0 | 0 / 0 | — | — |
| Requested union | 12 → 17 | 14 / 9 | 117.75 → 172.61 | 113.81 → 184.55 |

The full zeroed J values are 61,678.109 and 60,307.414; NLL is 60,808.932 and 59,775.558. The count increase coexists with worse residual RMS. The separate identity plot preserves all zeroed-state model labels.

![All assigned identity counts, c zeroing only](identity-histograms-zero-c-diagnostic.png)

## Code, verification and cost

[replay.py](replay.py) performed the no-fit reconstruction/evaluation in **20.5055 seconds**. It freezes inputs first, verifies all saved stage hashes and TLE payloads, preserves public selected-model calibration and q exactly, checks the original full-state arrays against their sealed predecessor, and checks every original row and requested denominator. [report.py](report.py) reads only the saved results to render CSVs and figures.

Two hardware-free component tests in [test_metrics.py](test_metrics.py) pass: new/lost/intersection versus stable-identity accounting, and immutable deterministic c zeroing. The actual public corpus loader was also exercised independently: both returned Contexts contain exactly 4,797 observations, 46/59 selected candidates and vector/nuisance arrays exactly equal to the pre-evaluation freeze.

[contexts.py](contexts.py) is the stable read-only loader for subsequent explicitly separate controlled experiments:

```python
from contexts import load_contexts
states = load_contexts(maximum_seconds=110.)
original = states['original']
saved = states['saved_space_track']
# Each exposes model, full_model, vector, nuisance, observations, bank and prior.
# Original physical correction: model.original.correction(vector, nuisance[:model.base_nuisance_count]).
```

The loader SHA-256 is `d66fe117dfc8ffe65841ecd0aaf2b6dba7cc4ddbafcc09d6ff15217e5d4d661c`. It reads public persisted evidence and the saved local run only; hardware and station configuration are not required. Local public source storage, the causal TLE archive and the saved temporary pipeline receipts must still be available. It does not execute the pipeline or select a new endpoint. The replay/loader use the pinned deployed scientific runtime, not either reference repository.

The executed test command was:

```bash
sudo -n env PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH=/opt/leo-fast-auto/f141dbb30321bc8f9e8183576c511431ea60a6b3/worker/src \
  OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  /opt/leo-tracker/releases/47e2705e437722daa5e6d6bb1c252d54b7a21dbc/.venv/bin/python \
  -m unittest discover -s reports/2026_10_17_dsx01_iteration7/cold_saved_s01 -p 'test_*.py' -v
```

This directory is sealed by `manifest.json`. The replay executable is a generation record; do not rerun it against these sealed output paths. Future experiments can use the read-only loader and write their own receipts elsewhere. No model is promoted by this audit.
