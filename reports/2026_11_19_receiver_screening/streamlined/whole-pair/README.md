# Same whole-IQ cavity on DS26 and DS29

Both ordinary recordings returned both positions and matched the earlier same-input secant cavity coordinates and RF RMS exactly. One **512 MiB, zero-swap** Linux service covered every stage of each run. The completed DS26 measurement is paired with a fresh DS29 replay of the same worker. The earlier DS29 full-recovery result remains a separate, later numerical endpoint. [Scientific comparison](comparison.json) · [Cgroup and stage evidence](stages.json.gz) · [Position charts](plots/README.md) · [DS29 full recovery](../../integration/whole-memory-chain/README.md)

| Host measurement | DS26-0036 | DS29-0082 |
|---|---:|---:|
| Recorded acquisition span (s) | 299.996 | 300.018 |
| Read, authenticate, decode and detect (wall s / CPU s) | 117.220 / 218.539 | 88.071 / 163.959 |
| Factor assembly and process handoff (wall s / CPU s) | 1.137 / 1.111 | 0.936 / 0.809 |
| Cavity position (wall s / CPU s) | 67.961 / 67.629 | 41.218 / 40.803 |
| Complete replay to positions (wall s / CPU s) | **186.319 / 287.278** | **130.225 / 205.571** |
| Replay wall / recorded span | 0.621 | 0.434 |
| Systemd service lifetime (s) | 187.388 | 131.226 |
| Peak cgroup bytes | 536,870,912 | 536,870,912 |
| Position process peak RSS (KiB) | 467,768 | 479,256 |
| Observed swap and OOM events | 0 | 0 |

The unchanged ordinary binary used one numerical thread per raw lane, at nice 10 on CPUs 18 and 19. The position path replaced the orchestrator under the same cgroup and continued on CPU 18 with a single numerical thread and the original measurement sampler. In DS29 the anonymous cgroup charge at the signed-context entry fell from 411,254,784 to 362,627,072 bytes after allocator trimming. Signed context returned at a total cgroup charge of 480,935,936 bytes. [Signed-context and cavity memory samples](stages.json.gz) · [Source and input lock](source-lock.json)

| Position stage wall (s) | DS26-0036 | DS29-0082 |
|---|---:|---:|
| Native preparation | 16.016 | 17.093 |
| Initial selection | 19.955 | 9.681 |
| Conservative recovery | 8.998 | 1.780 |
| Family history | 6.924 | 2.936 |
| Signed context | 2.250 | 1.981 |
| Cavity | 9.733 | 4.565 |

| Recording | Calibration arm | Latitude | Longitude | Horizontal error (km) | Conditional Doppler RMS (Hz) |
|---|---|---:|---:|---:|---:|
| DS26-0036 | `c = 0` | 37.850913218 | −122.486569706 | 0.218 | 102.253 |
| DS26-0036 | Fitted `c` | 37.850674200 | −122.485556782 | 0.180 | 102.289 |
| DS29-0082 | `c = 0` | 37.873858439 | −122.490523446 | 2.789 | 106.672 |
| DS29-0082 | Fitted `c` | 37.872828354 | −122.488485228 | 2.654 | 106.588 |

The two fresh native factor documents match their earlier ordinary whole-IQ archives byte for byte. Both calibrated fits use each recording's same retained factor document and offered tile. Capture-era factor digests remain distinct. The position charts show those original v5 choices under their capture-era authority. [Per-arm scores](scores.csv) · [Prediction lock](prediction-lock.json)

## Individual detector calls

| Native analyzer | DS26-0036 | DS29-0082 |
|---|---:|---:|
| Complete recorded visits | 6,769 | 6,772 |
| Valid native calls | 6,765 | 4,868 |
| Capture exclusions | 4 | 1,904 |
| Per-call wall median / p95 (ms) | 27.252 / 33.351 | 26.556 / 32.683 |
| Calls at most 20 ms | 86 / 6,765 | 44 / 4,868 |

Each complete replay took less wall time than its recording duration. The measured host detector exceeded 20 ms on most individual valid calls. These thresholds measure different stages. [Per-call durations](stages.json.gz)

## Archive authorities for a caller

The six existing ordinary receipts below pair each source-host archive inventory with its ordinary factor SHA-256. All 84 segment manifests and their inventory bindings were verified. Each recording had 212 declared IQ index and compressed payload members with matching local file types and sizes. The audit also rehashed each materialized ordinary factor file. The two capped replay receipts contain the actual compressed-content and decoded-window integrity checks from this worker. [Exact archive members and digests](archive-authority.json.gz) · [Archive audit lock](archive-authority-lock.json) · [Earlier ordinary receipts](../../../2026_11_19_receiver_frontend/ordinary/recording-receipts.json)

| Archive case | Saved visits | Pilot edge | Earlier ordinary factors on the host | Sealed same-ordinary secant cavity control |
|---|---:|---|---|---|
| DS26-0036 | 6,769 | Lower | Persistent archive scratch | Yes |
| DS26-0122 | 6,772 | Upper | Local temporary scratch | — |
| DS26-0237 | 6,768 | Lower | Local temporary scratch | — |
| DS29-0082 | 6,772 | Upper | Persistent archive scratch | Yes |
| DS29-0174 | 6,774 | Upper | Local temporary scratch | — |
| DS29-0247 | 6,775 | Lower | Local temporary scratch | — |

An authorized caller can supply the immutable segment manifests with their declared index and compressed members for IQ replay. The runtime source and exact ordinary detector digest are in the inventory. For a factor-only call the corresponding verified ordinary factor file must be paired with the original truth-free job, track settings and causal catalogue. Files in temporary scratch have the availability recorded at audit time. The qualification launcher uses the source host's local archive identity and a user systemd memory controller. The existing capture-era factor files represent a separate source authority. A third run was omitted because the four remaining ordinary archives lacked a sealed matching cavity control. [Recording port](../../../../tools/pipeline_eval/qualification/recording_to_v5.py) · [Whole-service entry](../../../../tools/pipeline_eval/qualification/whole_pair.py)

## Reproduce

```sh
.venv/bin/python -B -m tools.pipeline_eval.qualification.whole_pair seal
.venv/bin/python -B -m tools.pipeline_eval.qualification.whole_pair run
.venv/bin/python -B -m tools.pipeline_eval.qualification.whole_pair publish
.venv/bin/python -m tools.pipeline_eval figures --panel screening --arm both \
  --evidence reports/2026_11_19_receiver_screening/streamlined/whole-pair \
  --out /tmp/whole-pair-figures
.venv/bin/pytest -q tests/pipeline_eval/test_whole_pair.py
```

Choose a fresh `--runs` directory. The predeclared service deadline was 300 s. [Protocol](PROTOCOL.md)
