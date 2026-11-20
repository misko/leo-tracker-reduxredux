# A live deadline from stored GLRT detections to a position

The same DS26 recording exercised both ordinary completion and cancellation. With a 30-second limit, the supervisor stopped compact v5 after 15.02 seconds and published a smooth-clock position at 20.76 seconds. With 180 seconds on that recording, compact v5 finished in 115.40 seconds. On a second recording, the compact worker raised a numerical error after 137.90 seconds and smooth clock supplied a fix before the deadline. Each returned position and conditional Doppler RMS matched its independently archived solver exactly in both calibration settings. [30-second position chart](../charts/fitted_c/deadline_live-30s.png) · [180-second position chart](../charts/fitted_c/deadline_live-180s.png) · [Both-arm scores](scores.csv)

| Recording | Limit | Returned solver | Wall to result | Horizontal error, zero / fitted calibration | Conditional Doppler RMS, zero / fitted |
| --- | ---: | --- | ---: | ---: | ---: |
| DS26-0036 | 30 s | Smooth clock after compact timeout | 20.76 s | 0.650 / 0.442 km | 142.89 / 112.86 Hz |
| DS26-0036 | 180 s | Compact v5 | 115.40 s | 1.260 / 1.196 km | 74.76 / 74.68 Hz |
| DS26-0191 | 180 s | Smooth clock after compact fit failed | 147.53 s | 4.177 / 3.486 km | 281.18 / 256.09 Hz |

These three jobs were chosen to exercise the decision paths. Comparing error distributions across the same recording at two deadlines is possible here. Estimating how often each path occurs uses the separate 159-recording replay, whose times come from the two standalone archives. [159-recording timing model](../deadline-roof/README.md) · [Prospective live protocol](PROTOCOL.md)

The live stopwatch includes solver startup, cancellation and result handling. Binding the stored detector file, tracking configuration, causal orbital elements and offered tile before starting the stopwatch took 0.07–0.08 seconds. The numerical jobs used low-priority, pinned host CPUs. The launcher's child-CPU counter can omit CPU from a terminated grandchild, so the table uses measured elapsed time. The RF numbers describe different receiver-selected observations. On DS26-0036 the longer compact fit produced a smaller RF residual and a larger geographic error. [Short run](short.json) · [Long run](long.json) · [Numerical failure](failure.json)

The prediction seal covers the original three worker receipts before joining them to the survey. The scorer also compares the live endpoints with their matching standalone control. Both calibration arms share an offer and a routing decision. [Prediction seal](prediction-lock.json) · [Score seal](score-lock.json)

```sh
.venv/bin/python -m tools.pipeline_eval.qualification.deadline_live_results
.venv/bin/python -m tools.pipeline_eval figures --panel screening \
  --evidence reports/2026_11_19_receiver_screening/deployment/deadline-live \
  --out /tmp/receiver-live-deadlines
```
