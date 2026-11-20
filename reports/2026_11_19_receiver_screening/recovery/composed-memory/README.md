# One composed compact v5 worker at the 512 MiB gate

The composed worker finished unrestricted at **862 MiB peak process RSS** and reproduced both archived calibration-arm positions and radio fits exactly. Under an enforced **512 MiB** cgroup limit with swap disabled, it completed preparation and four discovery associations, then was OOM-killed during the fifth association. The capped attempt returned no position. [Exact comparison](comparison.json) · [Hard-cap trace](memory-cap.json) · [Position charts](plots/README.md)

The unrestricted and capped runs use the same numerical worker, pin, scientific request and authenticated ordinary native factors for DS29-0082. The scientific control is the sealed same-input tiled-salvage result from the earlier trial. Its runtime used a separate logical core. [Protocol](PROTOCOL.md) · [Source lock](source-lock.json)

The composition uses the existing bounded regional sky and final-use history cache, track-column projections for ranked search and family confidence, 16-satellite salvage tiles, and row-bounded late orbit recovery. The late recovery reads its existing unlinked scratch-backed states in bounded batches. The earlier whole-IQ measurement authenticated these ordinary factors before this trial. [Worker composition](../../../../tools/pipeline_eval/variants/v5_composed_memory.py) · [Whole-IQ authority](../../end-to-end/README.md) · [Archived control](../solver-memory/README.md)

## Unrestricted worker

| Completed boundary | Cumulative process peak RSS (KiB) |
|---|---:|
| Native preparation | 496,640 |
| Initial scan construction | 505,532 |
| Fresh discovery and initial selection | 590,132 |
| Conservative salvage | 590,132 |
| Family confidence | 882,412 |
| Complete compact finish | 882,412 |

The same-input archived tiled-salvage process peaked at 1,277,004 KiB. The fresh composed process used CPU 17, 87.03 CPU seconds and 113.29 wall seconds. The archived control used CPU 5. The composed late bank wrote 613.67 MB of temporary ECEF and TEME rows outside the corpus and read up to 2.34 MB of state at a time. Those scratch files can occupy filesystem cache outside process RSS. The highest process reading was already reached in family confidence. [Unrestricted receipt](uncapped-positions.jsonl.gz) · [Archived control receipt](control-positions.jsonl.gz)

The graph, causal prior, fine orbit arrays, native history, forecast, ranked branches, family confidence, salvage outcomes, ordered late state, residual decisions and reassociation outputs matched the archived control. Both calibration arms also matched their position, optimizer counts, associated-observation counts, conditional Doppler RMS and frequency objective. Geographic error was 2.784 km at `c = 0` and 2.651 km with fitted `c`. Conditional Doppler RMS was 106.670 and 106.587 Hz, respectively. Geography was scored after the predictions were sealed. [Scientific comparison](comparison.json) · [Per-arm scores](scores.csv)

## Enforced 512 MiB attempt

The same traced worker ran alone in a transient Linux cgroup with `MemoryMax=536870912` and `MemorySwapMax=0`. The cgroup reached exactly 536,870,912 bytes. Systemd reported `oom-kill` after 25.951 wall seconds and 24.947 CPU seconds. The last marker was the fifth `ScanLikelihood.association` entry within `fresh_discovery`, following four completed association calls. Preparation and scan construction had returned. The trace identifies the blocking stage and leaves the failed allocation itself unresolved. [Cgroup receipt and stage trace](memory-cap.json) · [Capped prediction status](capped-positions.jsonl.gz)

The earlier tiled-salvage cap trace stopped at `fresh_discovery` before its first reported exploration. The composed path keeps the projected track buffers smaller, while early association still retains candidate nominations and scan state. It reaches neither conservative salvage nor the late streamed banks under the cap. [Earlier cap trace](../solver-memory/memory-cap-trace.json)

## Reproduce

```sh
.venv/bin/python -B -m tools.pipeline_eval.qualification.composed_memory_trial seal
taskset -c 17 .venv/bin/python -B -m tools.pipeline_eval.qualification.composed_memory_trial replay
taskset -c 17 .venv/bin/python -B -m tools.pipeline_eval.qualification.composed_memory_trial cap
.venv/bin/python -B -m tools.pipeline_eval.qualification.composed_memory_trial publish
.venv/bin/python -m tools.pipeline_eval figures --panel screening --arm both \
  --evidence reports/2026_11_19_receiver_screening/recovery/composed-memory \
  --out /tmp/composed-memory-figures
.venv/bin/pytest -q tests/pipeline_eval/test_v5_composed_memory.py
```

Use a fresh `--runs` directory for each rerun. The capped step requires an available user systemd manager and its memory controller.
