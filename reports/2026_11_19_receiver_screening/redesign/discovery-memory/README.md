# Sparse v5 discovery reaches family confidence at 512 MiB

The same ordinary native factors for DS29-0082 produced identical unrestricted positions, conditional Doppler fits, and ranked and recovery decisions. Discovery peak process RSS fell from **590,132 to 521,436 KiB**. With a real **512 MiB** Linux cgroup and swap disabled, the worker completed all 28 discovery associations and conservative salvage. The cgroup then killed it in family confidence, before either position was returned. The archived composed worker stopped during association 5. [Exact comparison](comparison.json) · [Hard-cap trace](memory-cap.json) · [Position charts](plots/README.md)

## Retained association data

Each of the 28 original association calls profiled 1,680 candidate rows for each of 29 curved tracks. Their two dense FP64 residual and innovation matrices represent **29,998,080 bytes per association**. The revised loop calls the same profile, then copies the exact diagnostics for the visible passing candidates and original visible fallback. The retained 29–32 rows across all tracks occupy 18,088–19,296 bytes per association, including the row indexes. The largest original pair still exists transiently for one track and occupies 1,989,120 bytes. Scalar costs, track votes, ties, aliases, and ranking arithmetic stay identical. [Protocol](PROTOCOL.md) · [Worker source](../../../../tools/pipeline_eval/variants/v5_sparse_discovery.py) · [Per-association receipt](uncapped-positions.jsonl.gz)

| Measurement | Archived composed | Sparse |
|---|---:|---:|
| Native preparation cumulative peak RSS (KiB) | 496,640 | 496,352 |
| Live RSS after association 1 (KiB) | 505,920 | 495,996 |
| Live RSS after association 5 (KiB) | 582,696 | 521,736 |
| Live RSS after association 28 (KiB) | 590,288 | 521,744 |
| Discovery cumulative peak RSS (KiB) | 590,132 | 521,436 |
| Whole worker peak RSS (KiB) | 882,412 | 828,212 |
| Association CPU time summed over 28 calls (s) | 3.75 | 5.11 |
| Whole worker CPU / wall (s) | 87.03 / 113.29 | 116.30 / 147.79 |
| Late temporary bank writes (bytes) | 613,672,128 | 613,672,128 |

Both complete processes peaked in family confidence. Both ran on host CPU 17. The archive and fresh run had different scheduling priority, and unrelated preparation and recovery stages also ran longer on the fresh worker. The timings describe the observed runs. The sparse stage itself used RAM and generated zero temporary file bytes. [Archived composed receipt](control-positions.jsonl.gz) · [Unrestricted receipt](uncapped-positions.jsonl.gz)

## Calibration arms

The sealed science matched the graph, prepared sky, causal history, forecast, noise, ranked branches, family confidence, salvage, ordered late orbit states and reassociation decisions. Geographic scoring after the prediction seal gave 2.784 km at `c = 0` and 2.651 km with fitted `c` for both unrestricted runs. Their conditional Doppler RMS was 106.670 and 106.587 Hz, with 1,310 associated observations in each arm. The cap reached exactly 536,870,912 bytes at 43.958 service wall seconds and 42.020 CPU seconds. Its final trace marker was entry to `confidence_for`. [Per-arm scores](scores.csv) · [Prediction lock](prediction-lock.json) · [Capped result](capped-positions.jsonl.gz)

## Reproduce

```sh
.venv/bin/python -B -m tools.pipeline_eval.qualification.discovery_memory_trial seal
nice -n 10 taskset -c 17 .venv/bin/python -B -m tools.pipeline_eval.qualification.discovery_memory_trial replay
nice -n 10 taskset -c 17 .venv/bin/python -B -m tools.pipeline_eval.qualification.discovery_memory_trial cap
.venv/bin/python -B -m tools.pipeline_eval.qualification.discovery_memory_trial publish
.venv/bin/python -m tools.pipeline_eval figures --panel screening --arm both \
  --evidence reports/2026_11_19_receiver_screening/redesign/discovery-memory \
  --out /tmp/discovery-memory-figures
.venv/bin/pytest -q tests/pipeline_eval/test_v5_sparse_discovery.py
```

Use a fresh `--runs` directory. The inputs are bound to the archived complete-IQ replay and latest local source lock. The capped command uses a transient user systemd service with the memory controller enabled. All resource measurements are on the Linux replay host. [Source lock](source-lock.json) · [Whole-IQ authority](../../end-to-end/README.md)
