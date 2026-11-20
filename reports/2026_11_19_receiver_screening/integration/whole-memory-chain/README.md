# Saved IQ to two positions at 512 MiB

The complete ordinary DS29-0082 replay returned both positions in **203.217 s**, or **0.677×** its 300.018 s acquisition span. One Linux cgroup covered saved-IQ authentication, Zstd decode, both ordinary GLRT lanes, factor assembly, and row-major compact v5 positioning. Its effective limit and observed peak were exactly **536,870,912 bytes**. Swap occupancy and OOM counters remained zero. The measured scope is host replay from saved IQ. [Stage and cgroup evidence](stages.json.gz) · [Position charts](plots/README.md)

## DS29-0082 stages

| Stage | Wall (s) | Cgroup CPU (s) | Cgroup charge at return (MiB) |
|---|---:|---:|---:|
| Read, authenticate, decode and run ordinary GLRT | 101.083 | 179.302 | 420.75 |
| Assemble factors and bind/compile position | 0.884 | 0.853 | 455.58 |
| Replace orchestrator and enter position | 0.151 | 0.151 | 357.96 |
| Finish row-major compact v5 | 101.098 | 90.085 | 475.00 |
| Complete replay | **203.217** | **270.391** | **475.00** |

The complete service lifetime was 204.439 s. The raw lane processes used one core and one numerical thread each, pinned to CPUs 18 and 19 at nice 10. The CPU 18 position stage replaced the capped orchestration PID so its solver did not overlap an idle Python supervisor. The solver process's peak RSS was 545,932 KiB, including shared mappings. The cgroup peak describes charged resident memory and file cache. [Cgroup samples, lane membership, stage counters and service trace](stages.json.gz)

## Ordinary detector and position

The archived reader previously loaded an entire compressed chunk. The new route presents the same decoder with authenticated reads of at most 128 KiB. It verified 106 compressed members across all 14 segments, totaling 8.402 GB compressed and 10.835 GB decoded. The complete visit inventory contained 6,772 recorded visits, 4,868 processed and 1,904 capture exclusions. Every newly generated native factor byte matches the prior complete ordinary replay. The receiver retained the original tile, causal catalogue and truth-free request, with freshly bound native and output paths. [Input and source lock](source-lock.json) · [Archived ordinary whole replay](../../end-to-end/README.md)

| Calibration arm | Latitude | Longitude | Horizontal error (km) | Conditional Doppler RMS (Hz) | Associated observations |
|---|---:|---:|---:|---:|---:|
| `c = 0` | 37.873813244 | −122.490517270 | 2.784 | 106.670 | 1,310 |
| Fitted `c` | 37.872801177 | −122.488475495 | 2.651 | 106.587 | 1,310 |

Both positions and radio scores exactly match the sealed same-ordinary row-major worker. Original capture-era v5 used a different factor SHA-256, associated 929 observations, and gave errors of 0.567 and 0.517 km in those arms. Charts retain the original choices with their capture-era input authority. [Per-arm scores](scores.csv) · [Row-major position control](../../deployment/recovery-reads/README.md) · [Capture-era coordinates](../../end-to-end/capture-era-reference-positions.json)

The native analyzer's median and 95th percentile wall times were 29.362 and 37.639 ms across valid detector visits. Its median CPU time was 28.393 ms. Only 11 of 4,868 calls completed within the 20 ms visit duration. The 300 s result covers parallel replay plus positioning and the 20 ms result covers each measured native call separately. The timing receipt also records the upper middle sample of 29.365 ms for reproducibility. [Per-visit timings](stages.json.gz)

## Second recording

DS26-0036 produced a byte-identical ordinary factor file under the same cap. Its position worker was OOM-killed in signed context at 11:54:22 UTC, before the 11:54:43 UTC panel cutoff. The announced extension was unused. The DS29 result remained the sole completed whole-IQ position at the cutoff. [DS26 attempt](ds26/README.md) · [Panel cutoff](panel-cutoff.json)

## Reproduce

```sh
.venv/bin/python -B -m tools.pipeline_eval.qualification.whole_memory_chain seal
.venv/bin/python -B -m tools.pipeline_eval.qualification.whole_memory_chain run --case DS29-0082
.venv/bin/python -B -m tools.pipeline_eval.qualification.whole_memory_chain publish
.venv/bin/python -m tools.pipeline_eval figures --panel screening --arm both \
  --evidence reports/2026_11_19_receiver_screening/integration/whole-memory-chain \
  --out /tmp/whole-memory-chain-figures
.venv/bin/pytest -q tests/pipeline_eval/test_whole_memory_chain.py
```

Use a fresh `--runs` directory, a Linux user systemd manager with a memory controller, and the existing read-only archive identity. [Protocol](PROTOCOL.md) · [Prediction lock](prediction-lock.json)
