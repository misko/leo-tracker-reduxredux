# DS26 saved IQ to both cavity positions at 512 MiB

The new service replayed all DS26-0036 saved IQ and returned both ordinary secant cavity positions in **186.319 s**, or **0.621×** its 299.996 s acquisition span. One Linux service covered archive authentication, Zstd decoding, ordinary GLRT on both physical receivers, factor assembly, and lifetime-bounded cavity positioning. Peak cgroup charge was **536,870,912 bytes** with zero swap and zero OOM events. The earlier whole-IQ row-major recovery attempt on this recording ran out of memory in signed context and stays preserved. [Stage evidence](stages.json.gz) · [Earlier DS26 attempt](../whole-memory-chain/ds26/README.md) · [Position charts](plots/README.md)

## Stages and memory

| Stage | Wall (s) | Cgroup CPU (s) |
|---|---:|---:|
| Authenticate, decode and run ordinary GLRT | 117.220 | 218.539 |
| Assemble facts and bind/compile position | 0.973 | 0.957 |
| Replace the orchestrator and enter position | 0.164 | 0.154 |
| Finish lifetime-bounded cavity position | 67.961 | 67.629 |
| Complete replay | **186.319** | **287.278** |

Service lifetime was 187.388 s. The single-thread detector lanes used CPUs 18 and 19 at nice 10. The cavity worker replaced the existing capped PID on CPU 18 and used one numerical thread with its stage sampler. Its peak process RSS was 467,768 KiB. The same-input unrestricted secant cavity's archived process peak was 1,036,384 KiB. [Stage and service receipts](stages.json.gz) · [Earlier ordinary secant](../../end-to-end/README.md)

The numerical sampler observed **414,511,104 bytes** of anonymous charge before signed context and **330,477,568 bytes** after allocator trimming. During that interval cgroup charge fell from 535,261,184 to 451,223,552 bytes, with the same file charge. Signed context returned at 501,817,344 bytes, then the cavity policy completed. The endpoint boundary is the paired cavity result, before the residual additions and reassociation of the earlier row-major recovery path. [Lifetime source and input lock](source-lock.json)

## Calibrated results

All 6,769 visits reproduced the original ordinary factor bytes, including four capture exclusions, on both physical receivers. The fresh coordinates, per-arm RF RMS, branch and initial fit counts, graph counts, cavity offer and kernel digest matched the same-ordinary five-refresh secant cavity exactly. Original capture-era v5 uses a different native factor file. [Scientific comparison](comparison.json) · [Capture-era results](../../end-to-end/capture-era-reference-positions.json)

| Arm | Latitude | Longitude | Horizontal error (km) | Conditional Doppler RMS (Hz) |
|---|---:|---:|---:|---:|
| `c = 0` | 37.850913218 | −122.486569706 | 0.218 | 102.253 |
| Fitted `c` | 37.850674200 | −122.485556782 | 0.180 | 102.289 |

The native analyzer's median and 95th percentile wall times were **27.252** and **33.351 ms**, respectively. Median native-call CPU time was 27.130 ms. **86 of 6,765** processed visits met the 20 ms visit time in their individual native calls. The full replay time and the per-visit detector result answer separate timing questions. [Per-visit evidence](stages.json.gz) · [Verified scores](scores.csv) · [Score lock](score-lock.json)

## Reproduce

```sh
.venv/bin/python -B -m tools.pipeline_eval.qualification.whole_cavity seal
.venv/bin/python -B -m tools.pipeline_eval.qualification.whole_cavity run
.venv/bin/python -B -m tools.pipeline_eval.qualification.whole_cavity publish
.venv/bin/python -B -m tools.pipeline_eval.qualification.whole_cavity_scores
.venv/bin/python -m tools.pipeline_eval figures --panel screening --arm both \
  --evidence reports/2026_11_19_receiver_screening/integration/whole-cavity \
  --out /tmp/whole-cavity-figures
```

Use a fresh `--runs` directory and the existing Linux user systemd memory controller and read-only archive identity. These measurements cover one replay on the host. [Protocol](PROTOCOL.md) · [Prediction lock](prediction-lock.json)
