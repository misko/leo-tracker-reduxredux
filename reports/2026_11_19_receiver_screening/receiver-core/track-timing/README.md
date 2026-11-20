# Predicting pilot timing on Doppler tracks

On two confirmation roof recordings, extrapolating the last two pilot epochs on a wide-detector Doppler track predicted the next epoch within **two samples on 1,663 of 2,012** comparable observations. Using the earlier Doppler slope as an additional correction gave **1,636/2,012**. Shuffling the target epoch within its own receiver, channel, RF, edge and 30-second block gave **0/2,012**. At 10 MS/s the tolerance is 0.2 µs. The original frequency-only Graph provided the track membership from the full recording. [Plots](track-timing.pdf) · [Exact counts and runtimes](track-timing.csv) · [Protocol](PROTOCOL.md)

| Detector and confirmation recording | Graph-owned points | Triples meeting time limits | Passed the historical clock gate | Comparable targets | Within 2 samples, linear / Doppler / shuffle |
| --- | ---: | ---: | ---: | ---: | ---: |
| Capture-era DS26-0237 | 3,293 | 894 | 888 | 881 | 695 / 681 / 0 |
| Capture-era DS29-0174 | 3,587 | 951 | 947 | 936 | 750 / 731 / 0 |
| Wide DS26-0237 | 3,626 | 999 | 992 | 988 | 811 / 802 / 0 |
| Wide DS29-0174 | 3,762 | 1,034 | 1,033 | 1,024 | 852 / 834 / 0 |

The two confirmation wide streams yielded 6,916 consecutive triples. The interval and cadence requirements admitted 2,033. The clock gate rejected eight, and 13 other targets had no comparable shuffle partner. These restrictions matter when applying the result to a live receiver. Among the 2,012 comparable targets, even the one-sample criterion passed 1,580 times for the linear forecast and 1,337 times with the Doppler correction. The simple predictor also led on the DS26-0036 and DS29-0082 diagnostic waveforms. [Per-target predictions and negative controls](targets.jsonl.gz)

Each forecast uses two earlier pilot epochs, the native hardware counters, and the scheduled counter of the next sample. Only the corrected version uses the two earlier carrier-frequency measurements. Fractional frame length at 10 MS/s is respected by reducing integer counter differences modulo the 750 Hz frame cadence before converting to samples. Charge for reading the complete native document, checking all winners and scoring forecasts was 0.17–0.41 CPU seconds per detector/recording on one host core. It excludes the earlier Graph construction and original signal capture. The calculation uses neither position nor a learned RF calibration coefficient.

Both wide confirmation cases passed the prespecified threshold for testing real acquisition hints. A live detector must identify a plausible track and offer a usable pilot start before it processes the current samples. Its yield across all scheduled visits is measured separately. [Forecast implementation](../../../../tools/pipeline_eval/variants/track_epoch.py) · [Numerical evidence seal](result-lock.json) · [Causal tracker on eight full streams](../causal-track-scout/README.md)

The first data join stopped before forecasting. The native receiver IDs were zero-based on these recordings, while the original Graph maps sorted receiver IDs to one-based lane numbers. The corrected join uses that mapping and checks observation IDs, sample-clock times, channel, and lifted CFO for every owned point. A separate run with overwrite protection reproduced all 6,425 target records byte for byte and all 23 scientific summary fields on all eight input comparisons. [Initial join lock](initial-join/source-lock.json) · [Measured runner](measured-trial.py.gz) · [Replay checksums and fields](replay-check.json)

Regenerate the figure from the sealed timing table with the first command. The second command reruns the numeric trial with the original stored capture-era and wide factors in a fresh directory containing a copy of this protocol.

```sh
.venv/bin/python -m tools.pipeline_eval.qualification.track_timing_figure
.venv/bin/python -m tools.pipeline_eval.qualification.track_timing_trial --out "$TIMING_TRIAL"
```
