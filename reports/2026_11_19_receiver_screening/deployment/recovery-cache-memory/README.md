# Bound page-cache retention during late orbit-bank writes

The cache-bounded worker finished the first orbit bank and all residual screening at **512 MiB with zero swap**. It hit the 180-second service deadline while writing the second orbit bank for reassociation and returned no capped position. The previous worker was OOM-killed writing its first orbit bank. [Cgroup trace](memory-cap.json) · [Position charts](plots/README.md) · [Tiled nomination control](../nomination-memory/README.md)

The policy syncs completed scratch ranges and advises the kernel to evict their clean page-aligned bytes. The retained writes are identical to the tiled nomination control on ordinary DS29-0082. The orbit calculations, scratch readers, detector factors and both calibration arms are unchanged. [Protocol](PROTOCOL.md) · [Cache policy](../../../../tools/pipeline_eval/variants/v5_recovery_cache_memory.py)

## Unrestricted replay

All scientific checks passed exactly, including complete raw and refined family nomination digests, causal orbit bank hashes, residual recovery, reassociation, optimizer counts, conditional frequency scores and both positions. The two calibration arms gave 2.784 and 2.651 km horizontal error and separate conditional Doppler RMS values of 106.670 and 106.587 Hz. Both retained 1,310 associated observations. [Exact comparison](comparison.json) · [Per-arm scores](scores.csv)

| Host measurement | Tiled nomination | Bounded scratch cache |
|---|---:|---:|
| Complete process peak RSS (KiB) | 549,152 | 549,992 |
| Complete CPU / wall (s) | 97.54 / 101.07 | 118.44 / 188.95 |
| Complete scratch writes (bytes) | 613,672,128 | 613,672,128 |
| Page-aligned bytes advised for eviction | — | 613,654,528 |
| Maximum completed range per sync (bytes) | — | 9,363,456 |
| Data-sync calls | — | 72 |

The workers ran on CPU 17 at nice 10. The host workload varied across runs. The policy bounds dirty scratch cache in the service's working set, while process RSS measures the worker's resident pages. Scratch totals measure logical state writes across the two ECEF passes and TEME audit. [Control receipt](control-positions.jsonl.gz) · [Unrestricted receipt](uncapped-positions.jsonl.gz)

## Enforced 512 MiB replay

The service reached exactly 536,870,912 bytes of cgroup memory. Live samples showed zero swap and zero OOM events. The trace contains all 99 residual phase projections and the returned `screen_candidates` boundary. Reassociation then entered `late.stream_states#2`. The last marker was entry to `late.scratch_sync#30`, with 29 syncs complete. The 180-second deadline sent SIGTERM. The service lifetime including shutdown was 191.260 seconds and CPU use was 138.854 seconds. [Capped result](capped-positions.jsonl.gz) · [Live cgroup samples](live-cgroup-samples.txt)

A live kernel sample during the first residual screen showed 34.13 GB of physical storage reads and 204.91 MB of writes. Under the cap the service repeatedly reread the same state rows as it advanced through phase hypotheses. That read volume is a measured runtime bottleneck. [Live process I/O sample](late-io-sample.txt)

## Reproduce

```sh
.venv/bin/python -B -m tools.pipeline_eval.qualification.recovery_cache_memory_trial seal
nice -n 10 taskset -c 17 .venv/bin/python -B -m tools.pipeline_eval.qualification.recovery_cache_memory_trial replay
nice -n 10 taskset -c 17 .venv/bin/python -B -m tools.pipeline_eval.qualification.recovery_cache_memory_trial cap
.venv/bin/python -B -m tools.pipeline_eval.qualification.recovery_cache_memory_trial publish
.venv/bin/python -m tools.pipeline_eval figures --panel screening --arm both \
  --evidence reports/2026_11_19_receiver_screening/deployment/recovery-cache-memory \
  --out /tmp/recovery-cache-memory-figures
.venv/bin/pytest -q tests/pipeline_eval/test_v5_recovery_cache_memory.py
```

Use a fresh `--runs` directory and a Linux user systemd manager with the memory controller. This arm pair is one matched host replay. [Source lock](source-lock.json) · [Prediction lock](prediction-lock.json)
