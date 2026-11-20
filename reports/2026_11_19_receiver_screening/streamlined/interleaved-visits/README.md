# Three visits out of four on every channel

The receiver retained 28,970 of 38,625 valid dual-receiver visits across six five-minute recordings. It returned both calibration fixes on every recording. Against original no-repair v5, three of six zero-calibration fixes and four of six fitted fixes were within 10% of the original horizontal error or better. [Fitted-calibration position chart](../charts/fitted_c/interleaved-visits-roof6.png) · [Zero-calibration position chart](../charts/c0/interleaved-visits-roof6.png) · [Per-recording errors, RF and timings](scores.csv)

| Recording | Visits retained / valid | All visits, compact fitted error (km) | Three in four, fitted error (km) | Original v5 fitted error (km) |
| --- | ---: | ---: | ---: | ---: |
| DS26-0036 | 5,075 / 6,765 | 1.196 | 0.723 | 1.208 |
| DS29-0082 | 3,656 / 4,868 | 0.516 | 1.050 | 0.517 |
| DS26-0094 | 5,050 / 6,736 | 1.396 | 1.162 | 1.402 |
| DS26-0066 | 5,080 / 6,773 | 2.365 | 1.629 | 1.218 |
| DS29-0604 | 5,065 / 6,756 | 1.029 | 1.084 | 1.041 |
| DS29-0519 | 5,044 / 6,727 | 0.306 | 0.233 | 0.319 |

The first two IDs are development examples. The other four were drawn by a fixed hash before execution of this schedule. One drawn recording, DS26-0066, had previously been used to study late recovery in v5. On the four drawn inputs, zero and fitted median errors were 1.085 and 1.123 km, close to the original 1.113 and 1.129 km. Their P95 errors were 1.587 and 1.559 km versus the original 1.245 and 1.374 km. All four recordings share the same roof installation. [Prelaunch protocol](PROTOCOL.md) · [Roster and source binding](plan.json) · [Sealed predictions](prediction-lock.json)

Each sweep over eight bands drops two visits. Rotating which two are dropped gives every band three visits in four sweeps, without reading future RF evidence. The schedule retains each original timestamp and both receivers at each admitted visit. The six workers used the complete stored capture-era detector outputs and a compact secant fit. Their 48–72 s launcher intervals start after detection. In the separate raw-IQ experiments, the receiver actually skipped those detector calls and processed five minutes of saved IQ before returning positions. Those trials used the ordinary detector release and its own complete controls. [Matched end-to-end schedule and timings](../iq-schedule/README.md)

The RF and position effects can move in opposite directions. On DS29-0082, fitted RMS improved from 96.68 to 79.10 Hz as geographic error increased from 0.516 to 1.050 km. Across the four hash-selected inputs fitted median conditional RMS was 80.23 Hz with the schedule and 77.28 Hz on full compact. Their proximity to the original position is scored independently. [Frequency and geographic results](scores.csv)

```sh
.venv/bin/python -m tools.pipeline_eval run --panel smoke --case DS26-0036 \
  --variant interleaved_visits --timeout 165 --out /tmp/scheduled-position
.venv/bin/python -m tools.pipeline_eval figures --panel screening --variant interleaved-visits-roof6 \
  --out /tmp/scheduled-position-figures
```
