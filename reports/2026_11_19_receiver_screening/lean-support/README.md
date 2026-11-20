# Held-track evidence for the lean receiver

The guarded receiver did not improve coverage on eight fresh roof recordings. It issued six fixes in each arm, matching the lean control's coverage. With fitted calibration, four guarded and five lean fixes were within 5 km. All three receivers withheld every wrong-tile query. [Predictions](predictions.jsonl.gz) · [Prediction lock](prediction-lock.json)

The original receiver withheld five of eight earlier independent capture-era roof recordings and two of six ordinary-detector recordings. Every withheld case had four physical radio lanes, at least 31 assigned satellites and at least 27 curved assigned tracks. The conditional position radii were 1.36–2.14 km. Coverage failed at held-track prediction and at the change in position between training and pooling. [Archived decision audit](diagnostic.json)

| Prior cohort | Withheld by held mean score | Withheld by training-to-pooled shift | Issued |
|---|---:|---:|---:|
| Independent capture-era GLRT, 8 recordings | 2 | 3 | 3 |
| Ordinary native GLRT, 6 recordings | 2 | 0 | 4 |

Across the four weak held-score recordings, 45 of 81 held tracks assigned to a satellite already present in training met the 6.25 whitened-loss limit. Only 4 of 25 held tracks assigned to a previously unsupported satellite met the same limit. DS29-0082 passed on all five trained-satellite tracks and three of eleven untrained-satellite tracks. The original phase is zero for an unseen satellite. Allowing phase and identity to be profiled using the held observations recovered 100 of 106 tracks across those four recordings. That fit is a diagnosis of the loss, since the held data supply the additional fit. Three of the four cases also moved 7.15–15.84 km from training to pooling under the original lean model. [Archived decision audit](diagnostic.json)

The new receiver tests a contiguous block of original samples on each sufficiently supported track after reserving an eight-second guard. It predicts those samples using the orbit, phase, integer alias, and radio terms learned from the retained portions. Conditional residuals use the original correlated-noise model. The solution still requires support from at least two distinct held satellites, a small change on pooling, sufficient conditional geometry, and separation from the tile edge. The original lean and exact-orbit controls retain their prior criteria. [Protocol](PROTOCOL.md) · [Source lock](source-lock.json)

## Eight new roof recordings

Each pair in the table gives `c = 0` / fitted `c`. The methods used identical anonymous GLRT track and causal TLE packets within each query. All 48 fitter calls completed. The nearest eligible wrong-tile centers were 36.6–55.2 km from the reference sites. [Per-arm scores](scores.csv) · [Wrong-tile inventory](wrong-offers.json)

| Receiver | Issued / 8 | Within 5 km / 8 | Issued median (km) | Issued P95 (km) | Common-fix median (km) |
|---|---:|---:|---:|---:|---:|
| Lean robust EM | 6 / 6 | 5 / 5 | 1.862 / 1.751 | 4.758 / 4.927 | 1.608 / 1.735 |
| Exact orbit | 5 / 5 | 5 / 5 | 1.597 / 1.725 | 2.929 / 3.033 | 1.597 / 1.725 |
| Guarded track prediction | 6 / 6 | 5 / 4 | 2.451 / 2.317 | 8.025 / 8.124 | 2.115 / 1.768 |

Five recordings issued in all methods. All eight matched tiles passed the guarded held-sample test in both arms. The two withheld recordings failed the 4 km training-to-pooled position limit. The guarded solution for DS29-0316 had 16 supported held satellites and a fitted held score of 0.767, but its fitted position erred by 9.060 km, compared with 1.563 km from lean robust EM and 1.493 km from the exact orbit fit. Its training and final position estimates differed by 2.407 km. This isolates a limitation of conditional prediction within a selected Doppler basin. The stricter cross-satellite evidence still supported an inaccurate position. [Per-arm scores](scores.csv)

Median conditional in-sample Doppler RMS across all eight matched tiles was 225.723 / 225.441 Hz for lean robust EM, 183.772 / 174.671 Hz for exact orbit, and 235.044 / 235.016 Hz for guarded prediction. These RMS values use each method's selected rows, including diagnostic fits on withheld cases. The separate four-site synthetic transfer using capture-derived disturbances issued four correct offers with guarded prediction and two with exact orbit. Both withheld the paired omission and shuffle controls. The guarded improvement on that synthetic transfer did not carry over to the captured roof cohort. [Frequency and geographic summaries](summary.json) · [Synthetic transfer](../site-transfer/README.md)

| Receiver | Median CPU (s) | Median wall (s) | Peak RSS (KiB) |
|---|---:|---:|---:|
| Lean robust EM | 2.43 | 2.81 | 155,744 |
| Exact orbit | 2.57 | 3.03 | 155,660 |
| Guarded track prediction | 2.73 | 3.52 | 155,608 |

The measurements start with prepared anonymous tracks and end at the publication decision. Each worker used one pinned CPU and one numerical thread. The guarded receiver keeps two six-step assignment passes like the lean control, shortlists the additional retained fragments (36–53 per recording), and adds two training regressions and conditional predictions for their held observations. Correlated-noise whitening of each retained fragment uses a dense factorization. The extra work added 0.30 s median worker CPU time relative to the lean control on these inputs. The guarded receiver missed the preregistered captured-data acceptance criteria. [Measurement receipts](predictions.jsonl.gz)

## Reproduce

```sh
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
trial_cache=/srv/bulk/leo-dev/receiver-screening-20261119/lean-support-cache
taskset -c 10,11 .venv/bin/python -B -m tools.pipeline_eval.qualification.lean_support_trial seal --cache "$trial_cache"
taskset -c 10,11 .venv/bin/python -B -m tools.pipeline_eval.qualification.lean_support_trial trial --cache "$trial_cache"
taskset -c 10 .venv/bin/python -B -m tools.pipeline_eval.qualification.lean_support_trial score --cache "$trial_cache"
.venv/bin/pytest -q tests/pipeline_eval/test_robust_support.py
```
