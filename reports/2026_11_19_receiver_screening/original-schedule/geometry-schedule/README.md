# Original detector visits reserved by forecast geographic information

The selector increased mean predicted log-information gain from **0.990 to 1.183** at the same **2,353 original stereo calls**. Its later fast measurements favored the nominal offer by **−0.236 Hz per call**, compared with **+2.077 Hz per call** for matched hash. The signed forecast result was worse for the geometry selector on all six held recordings. [Forecast and selector measurements](stage.csv) · [Locked rule](rule-lock.json)

## Held position results

| Factors | Published per arm | Within +10% of v5, zero / fitted | Median error km, zero / fitted | P95 km, zero / fitted |
| --- | ---: | ---: | ---: | ---: |
| Geographic information | 5/6 | 3/6 / 3/6 | 0.534 / 0.526 | 2.904 / 2.974 |
| Matched hash | 6/6 | 4/6 / 3/6 | 0.592 / 0.638 | 2.176 / 3.482 |
| Full fast | 6/6 | 4/6 / 3/6 | 0.653 / 0.804 | 2.253 / 2.089 |
| Full original | 6/6 | 6/6 / 6/6 | 0.648 / 0.610 | 2.798 / 2.805 |

The geometry run on DS26-0255 hit its 150-second limit. That recording counts in both allowance denominators. Medians and P95 values describe the published fixes. On DS29-0082, geometry reached 3.473 and 3.485 km, matched hash reached 2.666 and 2.506 km, and full original reached 0.568 and 0.516 km. Both calibration arms used the same selected packets and compact search budget. Within the geometry arm, fitting `c` moved median RF RMS from 94.461 to 94.468 Hz and median position error from 0.534 to 0.526 km. [Both position distributions](charts/index.html) · [Prediction seal](prediction-lock.json) · [All four original v5 options](v5-references.csv) · [Separate RF and position scores](scores.csv)

## Causal forecast and matched control

At each recording start, the selector verifies the most recent TLE snapshot already collected. RX0 fast tracks from the preceding 30 seconds supply candidate satellite shapes and fit a constant carrier offset and linear clock slope for each candidate. It projects the same two nuisance columns out of the east/north Doppler gradients, averages sensitivities with up to five posterior-weighted candidates, and estimates the next measurement's local log-determinant gain. The current visit supplies its clock and RF only for this decision. Its fast winner can enter the next block's track construction.

A new original-call token arrives after each 16 valid stereo visits on an RF. The selector spends it when a visit enters the learned gain quantile or reaches the expiry visit. On the held recordings, 257 calls crossed the information threshold and 2,096 used the expiry visit. Hash uses the same RF and spent token windows. The geometry threshold was 0.90 because it tied 0.75 in the prespecified development score and the larger value won the tie. The six held recordings were reused from the adaptive-visits study at one roof. Their selected slots were sealed before reading archived original donor factors or evaluating their held Doppler margin. [Protocol](PROTOCOL.md) · [Per-recording slot seals and input lineage](source-lock.json)

To test the forecast, fit the same candidate satellite identities at the nominal center and a 30 km east displacement with each offer's own past nuisance terms. Compare the held fast CFO residual on the selected slot, keeping unsupported calls in the denominator. Of the 2,353 calls in each method, only 30 geometry and 34 hash calls corroborated one of the two forecasts within 3 kHz. The displaced-offer check measures local forecast separation at the selection boundary. [Displaced-offer forecast](stage.pdf)

A second check applied those locked forecasts to the actual original donor winners. Geometry corroborated 26 of 2,353 calls, and hash corroborated 34 of 2,353. Mean nominal advantage was +0.096 Hz and +2.283 Hz respectively. Geometry placed below hash on all six recordings in this check as well. [Original donor forecast comparison](original-forecast.csv)

## Measured selector latency and detector model

Selector wall time was 2.69–4.77 seconds per recording on parsed input, with 1.86–3.67 seconds of CPU time. Creating the causal orbit bank dominated. The ten blocks' association and projection took 32–52 ms of CPU time per recording. The detector model includes all 38,599 fast visits and the matched original call counts. It totals 1,881 CPU seconds for geometry and 1,889 for hash, compared with 657 measured fast detector CPU seconds. Original per-visit work comes from exact archived clocks on two anchors and a same-series projection on the other four. [Modeled detector work](modeled-detector.csv) · [Timed compact services](fit-resources.csv)

A buffered one-worker model at recorded arrivals finished 408/410 geometry and 404/410 hash original calls by 300 seconds on DS26-0237. It finished 295/297 in both modes on DS29-0082. Independent compact fits use complete selected archive packets. The serial model assumes retained I/Q until the original service completes and uses a constant matched median fast delay. [Recorded-arrival and projected CPU accounting](modeled-detector.csv)

## Reproduce the results

```sh
study=reports/2026_11_19_receiver_screening/original-schedule/geometry-schedule
MPLBACKEND=Agg .venv/bin/python -m tools.pipeline_eval.qualification.geometry_schedule_results \
  --work /srv/bulk/leo-dev/geometry-schedule-20261120
MPLBACKEND=Agg .venv/bin/python -m tools.pipeline_eval benchmark --study "$study" \
  --out /var/tmp/geometry-schedule-benchmark
```
