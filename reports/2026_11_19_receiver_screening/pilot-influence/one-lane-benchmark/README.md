# One antenna per visit from pilot search to position

This receiver searches the same four pilot timing regions as the stock detector. Each valid visit runs the detector on one physical antenna. Visits to the same RF alternate antennas. Both antennas remain installed, with their original RF tuning, sample counters and delivery times. The unused antenna contributes no detections. [Prospective comparison](PROTOCOL.md)

The 22 recordings comprise 11 DS26 and 11 DS29 recordings from the same surveyed roof. On all 22, the position worker ran on a stream assembled from the measured full detector outputs. On DS26-0014 and DS29-0082 a separate implementation also processed the original I/Q and ran through position. The combined benchmark uses the actual two raw runs and the other 20 reconstructed streams. Every method is compared with all four v5 options for its own recording. [Whole-waveform runs](../one-lane-whole/README.md) · [22 reconstructed fits](../one-lane-roster/README.md)

| Receiver | Median, zero / fitted (km) | 95th percentile, zero / fitted (km) | Within +10% of v5, zero / fitted | Fitted error within +10% and replay within recorded duration |
| --- | ---: | ---: | ---: | ---: |
| Original v5 no repair or selective gap | 0.739 / 0.724 | 1.760 / 1.769 | 22 / 22 | Full replay clock unavailable |
| Original v5 one or two omitted tracks | 0.703 / 0.695 | 1.760 / 1.769 | 22 / 22 | Full replay clock unavailable |
| Four on both antennas | 0.774 / 0.776 | 1.543 / 1.437 | 13 / 13 | 13/22 timed |
| Five on both antennas | 0.742 / 0.782 | 1.556 / 1.522 | 13 / 14 | 13/22 timed |
| Alternating extra search | 0.668 / 0.649 | 1.355 / 1.388 | 12 / 12 | 0/2 timed |
| One antenna per visit | 0.855 / 0.815 | 1.786 / 1.797 | 8 / 8 | 1/2 timed |

All 22 one-antenna runs published both positions. On the two direct runs, the saved-sample path reproduced every byte of the independent projected native input and all four endpoints. Fitted errors for one versus both antennas were 1.050 versus 0.755 km on DS26-0014 and 0.728 versus 2.346 km on DS29-0082. The one-antenna replays finished in 140.4 and 134.1 s, with 10,946 of 11,640 detector calls within 20 ms. Across all 22, fitted calibration changed this receiver's conditional RF RMS by a paired median −0.058 Hz and its position error by −4.3 m. [Direct receipts](../one-lane-whole/README.md) · [Paired measurements](direct-parity.csv)

## Compare position and time

The position charts include every recording in the curve denominator and show the median of published fixes. The 5% and 10% counts include any fix with error at or below the corresponding multiple of its own no-repair v5 error. Conditional frequency RMS, frequency objective and position changes under fitted calibration are reported separately. [Fitted position errors](charts/fitted_c/one-lane-benchmark-all.png) · [Zero-calibration position errors](charts/c0/one-lane-benchmark-all.png) · [Individual scores](scores.csv) · [Calibration effects](calibration-effects.csv)

The timing chart puts one complete raw-to-position replay on each dot. The horizontal axis divides measured processing time by the recorded span. The vertical axis divides geographic error by original v5's error on the same recording. The two criteria must hold on that recording to count as jointly successful. Replays use their recorded host core assignments. The 20 ms call metric measures the detector itself. A delivery-paced queue with finite capacity is measured in a separate experiment. [Position and elapsed time](budget.png) · [Timing and clock scopes](timing.csv) · [Per-recording accuracy and time](accuracy-and-time.csv) · [Actual versus projected positions](direct-parity.csv)

## Rebuild

```sh
MPLBACKEND=Agg .venv/bin/python -m tools.pipeline_eval benchmark --receiver one-lane --out /tmp/one-lane-benchmark
```

The command scores the checked-in receiver outputs, reads the original measured clocks, and regenerates both calibration views. Raw replays and detector construction are documented with the individual experiments. [Input checksums](inputs.json) · [Sample groups](roster.json) · [All methods and percentiles](summary.csv) · [Joint accuracy and time counts](budget-summary.csv)
