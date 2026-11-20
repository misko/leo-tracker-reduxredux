# Ordinary saved-IQ replay with three of four visits scheduled

Both scheduled saved-IQ runs returned both cavity positions under a real **512 MiB** Linux cgroup with zero swap and zero OOM. The schedule omitted about one quarter of the original valid native calls. It reduced total replay time on each recording and increased the horizontal error of all four fitted position results. Its effect on conditional Doppler RMS differed between DS26 and DS29. [Position charts](plots/README.md) · [Stage and per-visit evidence](stages.json.gz) · [Full ordinary controls](../whole-pair/README.md)

## Physical calls and end-to-position time

The schedule uses the recorded visit and channel before calling the original two-receiver ordinary GLRT. Both receivers share each scheduling decision. Every saved visit was authenticated and decoded. This work preserves the original approximately 300 s acquisition spans, all delivery clocks, and the four DS26 and 1,904 DS29 capture exclusions. Each replay used one capped service with the original CPU 18 and 19 raw lanes at nice 10 and the same cavity worker on CPU 18. [Protocol](PROTOCOL.md) · [Source and input lock](source-lock.json)

| Measurement | DS26 full → scheduled | DS29 full → scheduled |
|---|---:|---:|
| Complete saved visits | 6,769 → 6,769 | 6,772 → 6,772 |
| Valid native calls | 6,765 → 5,075 | 4,868 → 3,656 |
| Retained share of original valid calls | 75.02% | 75.10% |
| Raw authentication, decode and GLRT wall (s) | 117.220 → 100.238 | 88.071 → 81.111 |
| Raw cgroup CPU (s) | 218.539 → 181.760 | 163.959 → 142.506 |
| Cavity position wall (s) | 67.961 → 50.656 | 41.218 → 41.152 |
| Whole-to-position wall (s) | **186.319 → 152.428** | **130.225 → 123.676** |
| Whole cgroup CPU (s) | 287.278 → 233.570 | 205.571 → 184.706 |
| Whole wall / recorded span | 0.621 → 0.508 | 0.434 → 0.412 |
| Position process peak RSS (KiB) | 467,768 → 451,196 | 479,256 → 501,376 |

All four runs reached 536,870,912 bytes of cgroup charge. Scheduled service lifetime was 153.591 s for DS26 and 124.786 s for DS29. Raw CPU and end-to-position wall include actual work observed on the replay host. Host workload and the selected visits both affect the timing comparison. [Cgroup observations and process timings](stages.json.gz)

## Individual native-call timings

Wall statistics use only actual native calls. The p95 uses the nearest rank. Each at-most-20-ms column retains the executed denominator. The original denominator remains 6,765 valid calls for DS26 and 4,868 for DS29.

| Recording and mode | Wall mean / median / p95 (ms) | CPU mean / median / p95 (ms) | Within 20 ms |
|---|---:|---:|---:|
| DS26 full | 27.404 / 27.252 / 33.360 | 27.263 / 27.130 / 33.082 | 86 / 6,765 |
| DS26 scheduled | 29.220 / 28.794 / 36.381 | 28.481 / 28.272 / 34.857 | 44 / 5,075 |
| DS29 full | 26.880 / 26.556 / 32.690 | 26.527 / 26.323 / 31.874 | 44 / 4,868 |
| DS29 scheduled | 29.851 / 28.846 / 38.114 | 28.505 / 28.173 / 35.229 | 12 / 3,656 |

Measured native calls still usually exceed 20 ms. Across the original valid denominator the scheduled mean measured work per original visit was 21.37 ms CPU in DS26 and 21.41 ms CPU in DS29, assigning zero detector work to omitted calls. That accounting measures workload reduction. The wall timings above measure deadline attainment of calls that actually ran. [Timing comparison](comparison.json)

## Factor parity and calibrated positions

All retained per-receiver factors equal their earlier full ordinary rows exactly. Dropped valid visits emitted two empty audit envelopes with their original metadata. The solver input removes these pairs and restores only the original analysis digest and derived run ID. All other source and acquisition fields match. Independent byte verification reproduced each effective input by applying the canonical selector to its sealed full ordinary control. The stage receipt retains separate full, emitted-audit and effective input digests, including the before-and-after bookkeeping identifiers. [Factor digests, identities and per-channel support](stages.json.gz) · [Saved raw lane adapter](../../../../tools/pipeline_eval/qualification/iq_schedule_worker.py)

| Recording | Calibration | Scheduled coordinates | Horizontal error, full → scheduled (km) | Conditional Doppler RMS, full → scheduled (Hz) |
|---|---|---|---:|---:|
| DS26-0036 | `c = 0` | 37.850813849, −122.484230074 | 0.218 → 0.236 | 102.253 → 101.213 |
| DS26-0036 | Fitted `c` | 37.849993827, −122.483467485 | 0.180 → 0.226 | 102.289 → 101.152 |
| DS29-0082 | `c = 0` | 37.877540351, −122.497463345 | 2.789 → 3.330 | 106.672 → 113.060 |
| DS29-0082 | Fitted `c` | 37.877083640, −122.494609098 | 2.654 → 3.212 | 106.588 → 113.479 |

The scheduled DS26 data improved conditional Doppler RMS in both arms while their position errors rose. DS29 lost accuracy in both measurements. The charts retain the other original v5 choices under their capture-era detector authority. [Per-arm scores](scores.csv) · [Prediction lock](prediction-lock.json)

## Reproduce

```sh
.venv/bin/python -B -m tools.pipeline_eval.qualification.iq_schedule seal
.venv/bin/python -B -m tools.pipeline_eval.qualification.iq_schedule run --case DS29-0082
.venv/bin/python -B -m tools.pipeline_eval.qualification.iq_schedule run --case DS26-0036
.venv/bin/python -B -m tools.pipeline_eval.qualification.iq_schedule publish
.venv/bin/python -m tools.pipeline_eval figures --panel screening --arm both \
  --evidence reports/2026_11_19_receiver_screening/streamlined/iq-schedule \
  --out /tmp/iq-schedule-figures
.venv/bin/pytest -q tests/pipeline_eval/test_iq_schedule.py
```

Use a fresh `--runs` directory and the source host's authorized read-only recording identity plus user systemd memory controller. The matched control receipts contain the same ordinary detector and the same cavity endpoint.
