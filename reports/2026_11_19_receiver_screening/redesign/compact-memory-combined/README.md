# Combined discovery and family-width memory reductions

The combined worker reproduced both complete calibration-arm positions and radio fits exactly on authenticated ordinary DS29-0082 factors. It passed family confidence under a **512 MiB** no-swap cap. The cap killed the worker after history policy returned and before family nomination began. The intervening call in the frozen worker is `signed_context`, which asks for full-catalogue phase widths a second time. No capped position was returned in either arm. [Comparison](comparison.json) · [Hard-cap trace](memory-cap.json) · [Position charts](plots/README.md)

| Boundary or measurement | Archived composed | Sparse discovery only | Combined |
|---|---:|---:|---:|
| Native preparation cumulative peak RSS (KiB) | 496,640 | 496,352 | 496,428 |
| Ranked discovery cumulative peak RSS (KiB) | 590,132 | 521,436 | 511,488 |
| Family confidence cumulative peak RSS (KiB) | 882,412 | 828,212 | 511,488 |
| Family confidence live RSS at return (KiB) | 643,668 | 607,180 | 486,196 |
| Peak RSS already reached at nomination entry (KiB) | 882,412 | 828,212 | 817,572 |
| Complete process peak RSS (KiB) | 882,412 | 828,212 | 817,572 |
| Family confidence CPU (s) | 2.81 | 3.27 | 1.03 |
| Whole worker CPU / wall (s) | 87.03 / 113.29 | 116.30 / 147.79 | 109.69 / 125.44 |
| Late temporary bank writes (bytes) | 613,672,128 | 613,672,128 | 613,672,128 |
| Last blocking call at 512 MiB | Association 5 | Family confidence | Signed context |

Cumulative peaks carry forward from earlier stages. The combined worker's high-water rose by 306,084 KiB between the observed history-policy return and nomination entry. Its transient service completed 28 discovery associations and reached an exact 536,870,912 cgroup bytes, zero swap, after 40.089 wall and 38.825 CPU seconds. The trace brackets the cap failure. Source inspection locates `signed_context` between those markers and shows two full-catalogue width lookups. [Frozen call order](../../../../tools/pipeline_eval/variants/v5_core.py) · [Sparse-only cap evidence](../discovery-memory/memory-cap.json) · [Archived composed cap evidence](../../recovery/composed-memory/memory-cap.json)

All three unrestricted workers ran on host logical CPU 17. The two fresh variants used nice value 10. Their timings describe the measured processes under their recorded scheduling. The two new stages add no scratch files. The complete worker continues to use its pre-existing unlinked late orbit banks. Exact comparisons covered preparation, ranked branches, family confidence, salvage, late state and recovery, optimizer counts and both position and RF outputs. Position errors were 2.784 km at `c = 0` and 2.651 km with fitted `c`. Their separate conditional Doppler RMS values were 106.670 and 106.587 Hz. [Unrestricted receipt](uncapped-positions.jsonl.gz) · [Per-arm scores](scores.csv) · [Source lock](source-lock.json) · [Prediction lock](prediction-lock.json)

## Reproduce

```sh
.venv/bin/python -B -m tools.pipeline_eval.qualification.compact_memory_combined_trial seal
nice -n 10 taskset -c 17 .venv/bin/python -B -m tools.pipeline_eval.qualification.compact_memory_combined_trial replay
nice -n 10 taskset -c 17 .venv/bin/python -B -m tools.pipeline_eval.qualification.compact_memory_combined_trial cap
.venv/bin/python -B -m tools.pipeline_eval.qualification.compact_memory_combined_trial publish
.venv/bin/python -m tools.pipeline_eval figures --panel screening --arm both \
  --evidence reports/2026_11_19_receiver_screening/redesign/compact-memory-combined \
  --out /tmp/compact-memory-combined-figures
.venv/bin/pytest -q tests/pipeline_eval/test_v5_compact_memory_combined.py
```

Choose a fresh `--runs` directory. The cap uses the Linux user systemd manager and memory controller. [Protocol](PROTOCOL.md)
