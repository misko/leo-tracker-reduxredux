# Start causal orbit preparation before the final factor input

On two stored ordinary inputs, moving causal orbit preparation earlier reduced measured factor-release-to-result time from **79.60 to 57.53 s** on DS26-0036 and **47.35 to 31.61 s** on DS29-0082. Both runs reused the early bank. All four paired coordinates, conditional Doppler RMS values, frequency scores and recorded decision counts matched the fresh direct cavity control exactly. [Timing measurements](timing.csv) · [Both calibration charts](charts/index.html) · [Exact parity](comparison.json)

## Causal boundary

The opening UTC anchor came from the first physical delivery envelope. The receiver can derive the original causal catalogue cutoff and UTC midpoint as soon as this bracket is available. With that anchor, the configured search screen and 300-second nominal acquisition schedule, it can parse causal TLEs, build the regional SGP4 state bank and earlier-orbit priors, read the selected families' phase history and forecast their phase. This preparation receives clock, screen and archive inputs. GLRT observations, selected peaks, tracks and noise enter only in the finishing call. [Prepare and finish interface](../../../../tools/pipeline_eval/variants/v5_causal_startup.py) · [First-visit and input seal](source-lock.json)

The original sky builder chooses the larger of 300 seconds and the final fitted track's last sample time. Its full grid can change for any extension beyond 300 seconds. The finishing call checks that horizon, the original clock authority, the screening center and ownership of the same immutable archive reader. A mismatch releases the provisional bank and runs the full original preparation. This leaves later Graph tracking, noise estimation, conservative fitting, signed history, family choice and both calibration arms on the original numerical path. Both measured final fitted horizons were 300 seconds. Tests deny access to future fields during preparation and exercise the rebuild on a late track. [Component tests](../../../../tests/pipeline_eval/test_v5_causal_startup.py)

## Measured shifted release

Each worker had a fresh process, one pinned CPU, one BLAS thread and nice 10. Case order alternated between stock first on CPU 20 and startup first on CPU 21. The native-factor path was delivered in a pipe 20 seconds after launching each worker. The replay parent authenticated the immutable factor and catalogue archives before the experiment. The worker used the predeclared factor checksum when it opened the final input, and the early scientific interface never received the factor file or its checksum. These elapsed times run from the real pipe release to both returned positions on a shared host. The experiment models moving work earlier during acquisition using a shifted release of stored factors. It measures neither concurrent live acquisition nor a memory-capped receiver.

| Measurement | DS26-0036 stock → early | DS29-0082 stock → early |
|---|---:|---:|
| Factor release to both positions (s) | 79.60 → 57.53 | 47.35 → 31.61 |
| Native preparation after reading the final factors (s) | 17.59 → 2.18 | 22.04 → 1.09 |
| Worker CPU spent in preparation and the fit (s) | 66.65 → 67.91 | 42.60 → 43.65 |
| Resident set when ready to consume final factors (MiB) | 235.2 → 508.9 | 235.1 → 575.2 |
| Peak process RSS over the worker (MiB) | 1,015.5 → 992.8 | 916.2 → 893.0 |

On DS26 the early sky, history and forecast took 10.48, 4.28 and 0.33 s. Preparation was ready 1.48 s before factor release. The DS29 stages took 12.48, 5.51 and 1.05 s and were still running for 2.27 s after release. The table includes that delay. Startup carries about 274 MiB more resident memory during the DS26 wait and 340 MiB more at DS29 readiness. These are process RSS observations. Summing that state with a concurrent detector or applying a hard memory cap requires a separate measurement. [Protocol](PROTOCOL.md) · [Per-stage and memory rows](timing.csv)

| Recording | c0 / fitted geographic error (km) | c0 / fitted conditional Doppler RMS (Hz) |
|---|---:|---:|
| DS26-0036 | 0.218 / 0.180 | 102.253 / 102.289 |
| DS29-0082 | 2.789 / 2.654 | 106.672 / 106.588 |

The paired geographic and radio numbers apply to both timings. The chart includes the four original v5 policies from their separate capture-era measurements. [Per-arm scores](scores.csv)

## Reproduce

```sh
.venv/bin/python -m tools.pipeline_eval.qualification.causal_startup_results \
  --published reports/2026_11_19_receiver_screening/next/causal-startup \
  --out /tmp/causal-startup
.venv/bin/pytest -q tests/pipeline_eval/test_v5_causal_startup.py
```

For another two-arm timing on the source host, use `causal_startup_replay seal --work <new-local-work>` and then `run` with the same work directory. Point `TMPDIR` at fresh local bulk scratch before compiling or running. The timed experiment requires the authenticated original ordinary inputs and their first-delivery envelopes. Scoring and rendering use the packaged outcomes. [Prediction lock](prediction-lock.json)
