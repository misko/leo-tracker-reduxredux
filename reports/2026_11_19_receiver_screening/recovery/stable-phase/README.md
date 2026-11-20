# Stop orbital updates when the receiver and satellites have settled

On six complete native-GLRT-to-position replays, the compact receiver skipped **14 of 120 orbital updates**. All 12 final coordinates and all 12 conditional Doppler RMS values matched five-update compact v5 exactly. Only the initial and conservative salvage fits used the new stop rule. Both the reference and the candidate ran the remaining stages through the cavity decision. [Protocol](PROTOCOL.md) · [Per-recording geographic and RF scores](scores.csv)

| Recording | Updates skipped out of 20 | Candidate horizontal error, zero / fitted calibration (km) | Complete worker CPU, five updates → candidate (s) |
| --- | ---: | ---: | ---: |
| DS26-0036 | 0 | 1.260 / 1.196 | 74.40 → 72.68 |
| DS29-0082 | 5 | 0.568 / 0.516 | 46.59 → 52.11 |
| DS26-0255 | 1 | 0.383 / 0.420 | archival control |
| DS26-0150 | 2 | 0.519 / 0.522 | archival control |
| DS29-0357 | 4 | 0.436 / 0.434 | archival control |
| DS26-0016 | 2 | 1.365 / 1.393 | archival control |

The two timing controls were rerun on the same host cores as their candidates. The total wall times were 80.13 → 79.84 s on DS26-0036 and 48.66 → 55.66 s on DS29-0082. Both fresh controls reproduced their archived positions and RF metrics. The other four recording IDs were selected by a fixed hash before running and use the earlier five-update receiver's authenticated outputs. Across all six cases, the number of position objective evaluations fell from 4,703 to 4,661 (0.89%). The reduction in work was too small to establish a host speedup on the two timed pairs. [Resources and stage times](resources.csv) · [Prediction lock](prediction-lock.json)

The median returned error was 0.544 km with `c = 0` and 0.519 km with fitted `c`. At the individual recording level, the median signed fitted-minus-zero change was +0.24 m in position error and +0.017 Hz in conditional RF RMS. Both arms used the same observations, initial candidate sets and maximum search budget. The [separate 135-recording audit](../phase-history-audit/README.md) measures the effect on the initial stage only. [Two timing recordings](../charts/fitted_c/stable_phase-timing.png) · [Four confirmation recordings](../charts/fitted_c/stable_phase-confirmation.png) · [Both chart definitions](figures.json)

From the repository root, the archived charts can be reproduced with the following command.

```sh
.venv/bin/python -m tools.pipeline_eval figures --panel screening \
  --evidence reports/2026_11_19_receiver_screening/recovery/stable-phase \
  --out /tmp/stable-phase-charts
```
