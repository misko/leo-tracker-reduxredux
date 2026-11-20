# Spectral grid partial-IQ position confirmation

The spectral detector was rerun on eight scheduled 20 ms visits per recording from the original development and holdout schedules. Every complete detector payload reproduced its qualification digest. All fresh fractional factors matched the corresponding capture-era archive factors exactly. The position trial used those freshly computed factors at the selected visits and archived detector output for the remainder of each recording. [Protocol](PROTOCOL.md) · [Original detector evidence](../../2026_11_19_receiver_frontend/spectral/README.md)

The capture clock brackets place DS26-0036 on 2026-10-25 and DS29-0082 on 2026-11-03, both UTC. The global visits are 1024, 1025, 1027 and 1030 in development and 6144, 6145, 6147 and 6150 in holdout. [DS26 fresh detector receipt](DS26-0036/spectral-replay.json.gz) · [DS29 fresh detector receipt](DS29-0082/spectral-replay.json.gz)

| Recording | Scheduled visits | Fresh valid IQ | Reproduced exclusions | Other valid visits from archive | Fresh receiver probe rows |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS26-0036 | 8 | 8 | 0 | 6,757 | 16 |
| DS29-0082 | 8 | 6 | 2 | 4,862 | 12 |

The control runs used the complete original capture-era archive. The spectral composites each received a distinct native input digest. Both versions used the full frozen no-repair v5 path, causal orbit catalogue and original roof search tile, with the same input, search budget and priors across calibration arms. The native input hash was checked against the actual worker request, and the comparison checks the complete prepared observation and track digests and the final observation-to-satellite ownership in each arm. Geographic truth enters only in post-fit scoring.

## Position and RF fit

Both spectral composites reproduced the control coordinates and conditional Doppler RMS exactly in each arm. DS26 had 3,395 prepared observations and 94 tracks, with 2,690 observations associated in each arm. DS29 had 1,868 prepared observations and 61 tracks, with 929 associated in each arm. Prepared tracks, observations, and final satellite ownership matched the paired controls by digest. [Spectral positions](positions.jsonl.gz) · [Capture-era control positions](control-positions.jsonl.gz)

| Recording | Calibration arm | Latitude | Longitude | Geographic error, km | Conditional Doppler RMS, Hz | Frequency score |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| DS26-0036 | `c0` | 37.853054831 | -122.499403041 | 1.278365 | 74.760916 | 25232.145635 |
| DS26-0036 | `fitted_c` | 37.852100070 | -122.498960650 | 1.208143 | 74.682298 | 25232.285586 |
| DS29-0082 | `c0` | 37.845496107 | -122.481132744 | 0.566947 | 97.003569 | 6337.717528 |
| DS29-0082 | `fitted_c` | 37.849671446 | -122.479915817 | 0.517230 | 96.683622 | 6342.809181 |

Across the two recordings, median geographic error was 0.922656 km for `c0` and 0.862686 km for `fitted_c`. The interpolated 95th percentiles were 1.242794 and 1.173597 km. The spectral and control distributions have the same two points in each arm. [Error distributions](error-distributions.json)

## Runtime

| Recording | Spectral IQ CPU / wall, s | Control v5 CPU / wall, s | Spectral composite v5 CPU / wall, s |
| --- | ---: | ---: | ---: |
| DS26-0036 | 5.97 / 6.04 | 208.35 / 212.37 | 223.88 / 229.54 |
| DS29-0082 | 5.12 / 5.12 | 151.79 / 156.61 | 122.14 / 122.68 |

The IQ times sum the detector calls over the eight scheduled visits per recording and exclude archive reads and compilation. The v5 times cover fresh paired workers pinned to CPUs 12 and 13. The pairs ran concurrently with opposite within-pair execution orders. These are individual runtime measurements for the position confirmation. The original detector report contains the repeated timing comparison.

## Reproduction

Run `tools.pipeline_eval.qualification.spectral_position` with `--case DS26-0036` or `--case DS29-0082`, its installed producer first on `PYTHONPATH`, numerical thread counts of one, and affinity to CPU 12 or 13 respectively. Set `--out` to a new per-case directory under a common parent. Then invoke the same module with `--package --out` and the common parent. The expanded numeric inputs and worker traces for this run are archived under `/srv/bulk/leo-dev/spectral-grid-position-atlas-20261119-4eeYII`. The compact receipts retain digests for the worker requests, both native inputs, and fresh IQ detector outputs.
