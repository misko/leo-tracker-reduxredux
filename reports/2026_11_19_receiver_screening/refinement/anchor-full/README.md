# Independent anchors on the full native roof panel

The frozen anchor receiver completed all 144 stored native GLRT requests through the streaming Graph front end in 107.1 seconds. It kept about half the observations of the full joint receiver and reduced median worker CPU from 5.00 to 3.21 seconds. The full joint receiver published eleven more correct-tile fixes in each calibration arm and had a smaller worst error. Both withheld every omitted offer. [Sealed predictions](positions.jsonl.gz) · [Summary and distributions](summary.json)

| Receiver and arm | Published / 135 | Within 5 km / 135 | Published median / P95 / max (km) | Wrong-tile publications / 9 |
|---|---:|---:|---:|---:|
| Independent anchors, zero | 108 | 103 | 1.800 / 4.810 / 11.485 | 0 |
| Independent anchors, fitted | 108 | 104 | 1.579 / 4.530 / 11.073 | 0 |
| Archived native joint, zero | 119 | 114 | 1.759 / 4.695 / 6.044 | 0 |
| Archived native joint, fitted | 119 | 114 | 1.584 / 4.723 / 6.194 | 0 |
| Original v5 baseline, zero | 135 | 133 | 0.982 / 2.941 / 7.269 | — |
| Original v5 baseline, fitted | 135 | 133 | 0.988 / 2.819 / 6.858 | — |

Among the 100 roof fixes both native methods published, median anchor minus joint error was +0.054 km with zero calibration and +0.049 km with fitted calibration. All four original v5 policies were within 5 km on 133/135. The chart retains all scheduled attempts. [Full roof figure](figures.json) · [Anchor scores](scores.csv) · [Matched native joint scores](stock-scores.csv)

The two calibration books collect the prepared, full-native and separate near-edge results. [Zero-calibration roof](rendered/c0/modifications.pdf) · [Fitted-calibration roof](rendered/fitted_c/modifications.pdf) · [Zero-calibration omitted controls](rendered/c0/transfer.pdf) · [Fitted-calibration omitted controls](rendered/fitted_c/transfer.pdf) · [Render seal](rendered/render-lock.json)

The two native methods used identical native, catalogue and offer checksums on all 144 requests. All 144 rebuilt Graph observation digests also matched. The anchor numerical source is identical to the earlier eight-case prepared-track trial. The full panel includes those eight recordings and 127 further roof recordings. The streamed and stored prepared projections had different serialized digests on the eight paired captures, while both calibration arms reproduced their exact eight decisions, positions and selected-observation counts. All 135 measured roof recordings are from the same installation. [Frozen protocol](PROTOCOL.md) · [Input plan](plan.json) · [Prepared-track comparison](../anchor-receiver/README.md)

| Native fit resource or frequency measure | Independent anchors | Archived native joint |
|---|---:|---:|
| Median observations used, 135 roof recordings | 1,908 | 3,696 |
| Conditional CFO RMS median, zero / fitted (Hz) | 146.5 / 120.5 | 182.6 / 159.2 |
| Median CPU, roof (s) | 3.208 | 4.999 |
| P95 worker wall, roof (s) | 5.143 | 7.149 |
| Peak RSS, all 144 requests (MiB) | 139.9 | 150.0 |
| Peak virtual memory, all 144 requests (MiB) | 375.4 | 385.6 |

The archived joint runtimes came from its separate sealed replay. Both report the native factor reader, Graph projection and position worker under a 512 MiB address-space cap. The anchor's largest observed worker wall time was 6.57 seconds. Conditional CFO uses the tracks each method selected. The earlier shared-point RF comparison found gains in one four-case group and regressions in the other. Lower conditional CFO and smaller support alone did not improve full-panel coverage or position tails. [Shared-point RF comparison](../anchor-receiver/matched-rf.json) · [Stock seal](stock-original-prediction-lock.json)

On the nine omitted offers, five anchor fits withheld at the tile edge and four withheld for weak position geometry. The median fitted-arm forced position error was 30.735 km. Forced endpoints are shown separately on the omitted control figure. On a separate sealed panel the same receiver published three of twenty omitted offers in each calibration arm. [Omitted queries](omitted-queries.json) · [Prediction lock](prediction-lock.json) · [Independent near-edge panel](../anchor-near-edge/README.md)

## Reproduce

```bash
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
scratch="$(mktemp -d)"
taskset -c 2,3,6,10,11 .venv/bin/python -m tools.pipeline_eval.qualification.anchor_receiver_full --work "$scratch/panel" --output "$scratch/report"
.venv/bin/python -m tools.pipeline_eval.qualification.anchor_receiver_full_results --work "$scratch/panel" --output "$scratch/report"
```
