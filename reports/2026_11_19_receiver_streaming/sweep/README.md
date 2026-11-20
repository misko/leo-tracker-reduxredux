# Alternating complete eight-channel sweeps

Keeping every second sweep produced fixes within 5 km on all six recordings in both calibration arms. Fitted-calibration median error rose from 0.832 to 1.181 km and P95 rose from 1.395 to 3.220 km against the full-cadence cavity control. The largest fitted loss was DS29-0082, from 0.517 to 3.343 km. DS26-0122 rose from 0.747 to 2.853 km. Four of six recordings worsened in each arm. [Position rows](position-errors.csv) · [Summary](summary.json)

| Schedule or control | Fixes / within 5 km, zero | Median / P95 / max km, zero | Fixes / within 5 km, fitted | Median / P95 / max km, fitted |
|---|---:|---:|---:|---:|
| Original full numerical v5 | 6 / 6 | 0.818 / 1.309 / 1.320 | 6 / 6 | 0.832 / 1.395 / 1.458 |
| Full eight-channel cavity v5 | 6 / 6 | 0.818 / 1.309 / 1.320 | 6 / 6 | 0.832 / 1.395 / 1.458 |
| Alternating eight-channel sweeps | 6 / 6 | 1.206 / 3.154 / 3.255 | 6 / 6 | 1.181 / 3.220 / 3.343 |
| Odd channels, every sweep | 6 / 6 | 1.138 / 1.689 / 1.804 | 6 / 6 | 1.222 / 1.740 / 1.861 |
| Even channels, every sweep | 6 / 4 | 2.970 / 12.778 / 15.309 | 6 / 4 | 2.941 / 12.785 / 15.324 |

Median conditional Doppler RMS was 79.940 Hz at zero calibration and 79.831 Hz with fitted calibration. The corresponding full-cadence medians were 78.443 and 78.409 Hz, computed on that schedule's own observations. Within the alternate-sweep schedule, fitting calibration changed RMS by a paired median of −0.119 Hz, lowering it on five of six recordings. Position error changed by a paired median of −0.025 km, with two recordings worsening. [Conditional frequency rows](conditional-frequency-rms.csv)

The schedule starts at visit zero. It keeps all eight channels and both antennas on alternate complete sweeps. Across the six recordings it retains 20,304 of 40,630 scheduled visit slots (49.97%) and 19,298 of 38,641 processed visits (49.94%). The archive marked 1,006 retained slots as invalid. Every recording retains a scheduled time span of at least 299.34 seconds. The previous 80-window tests scheduled 80 windows per recording. The visit counts here come from archived detector and capture-status records. Physical RF on-time, retune behavior and detector latency under the new schedule were outside the replay. [Visit load](visit-load.csv) · [Prior 80-window tests](../../2026_11_19_receiver_duty/README.md)

Graph tracking assigned 8,620 points to 450 tracks, down from 20,127 points on 681 tracks with full cadence. On each recording the median original track kept about half its detections. Retracking left 199 original tracks without any observation in a new track. Only one original track retained fewer than two observations, and 14 shared observations with more than one new track. DS29-0082, which had the largest position loss, went from 61 to 34 tracks and from 30 to 16 with active curvature. [Track support by recording](track-support.csv) · [Per-track overlap counts](positions.jsonl.gz)

Each replay used the cavity solver from the archived full-channel controls, verified against their SHA-256. The solver used the archived clocks, full 300 s orbit screening duration, causal catalogue and region. Retracking and association ran on the scheduled visits before both calibration fits. The shell used nice priority +19 and one numerical thread per pinned CPU. Worker wall times in the receipts include an additional full-graph pass for track support and came from a different batch than the archived controls. The wrapper was reformatted after execution. Its syntax tree matched the measured version after normalizing the order of four imports. [Predeclared protocol](PROTOCOL.md) · [Pinned cavity source](cavity-source.py.gz) · [Worker receipts](positions.jsonl.gz)

Rescore the shipped receipts or rerun the replay on a host with the bound corpus. The three historical scheduled and unscheduled controls are read from the earlier qualification receipts.

```sh
.venv/bin/python -m tools.pipeline_eval.qualification.sweep_trials --score-only
nice -n 19 .venv/bin/python -m tools.pipeline_eval.qualification.sweep_trials \
  --scratch /tmp/receiver-sweeps --cpus 4 5 6 7 8 9
```
