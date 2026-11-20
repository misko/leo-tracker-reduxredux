# Row-major late orbit screening

The ordinary DS29-0082 replay changes how the complete compact v5 worker reads ECEF rows during late residual screening and reassociation. A 128-row position and velocity block stays resident across all phases of one target or track. Each orbit retains its original phase and fold reduction order. Global candidate ranking, fine phase and alias evaluation, admission, propagation audit and scratch writes use the original paths. [Protocol](PROTOCOL.md)

The first ECEF bank has 11,185 usable satellite rows and 381 time knots. The original residual sequence queries three targets at 33 phases each. The reassociation screen queries two tracks at 31 phases each. Both coarse sweeps originally loaded all ECEF rows per phase. The new sequence reads 1,022,756,400 logical bytes across those five sweeps, down from 32,932,756,080 bytes calculated from the original access count. The largest resident raw state tile is 2,340,864 bytes. These counts cover the coarse sweeps. Fine queries and the audit still have their own reads. [I/O measurements](io-summary.json)

| Unrestricted replay | Bounded-cache control | Row-major reads |
|---|---:|---:|
| Whole-worker CPU (s) | 118.44 | 86.48 |
| Whole-worker wall (s) | 188.95 | 96.83 |
| Process peak RSS (KiB) | 549,992 | 546,940 |
| Residual screening CPU (s) | 36.90 | 17.24 |
| Reassociation screening CPU (s) | 16.79 | 6.05 |
| Three orbit bank writes, logical bytes | 613,672,128 | 613,672,128 |

The archived control ran on CPU 17 and the new worker ran on CPU 14, both at nice 10. The runs took place at different times on a shared host. The new unrestricted worker recorded 656,752,640 whole-worker physical read bytes through Linux process I/O accounting. The original capped worker had already read 34,127,937,536 physical bytes before all residual sweeps finished. [Original cap sample](../recovery-cache-memory/late-io-sample.txt)

The unrestricted worker reproduced both positions exactly, with 2.784 km at (c=0) and 2.651 km with fitted (c). Conditional Doppler RMS was 106.670 and 106.587 Hz, respectively, using 1,310 associated observations in each arm. Ordered bank digests, complete nominations, residual and reassociation evidence, audit and optimizer counts matched the sealed bounded-cache control. The standard chart also shows the four original v5 policies on capture-era factors. [Comparison](comparison.json) · [Scores](scores.csv)

## Enforced 512 MiB and zero swap

The capped Linux service returned both positions and all checked scientific quantities exactly. It completed in 93.55 s service wall, including 84.66 s of measured worker CPU. The complete worker recorded 3,221,762,048 physical read bytes and 614,739,968 physical write bytes. The unrestricted and capped workers used the same native factors, original offered tile, causal catalogue and normalized scientific request. [Capped prediction](capped-positions.jsonl.gz) · [I/O and equality checks](io-summary.json)

Fourteen live observations tied the worker PID to the transient service cgroup. They show effective `memory.max` of 536,870,912 bytes, cgroup peak at that value, zero swap limit and occupancy, and zero OOM events observed. The base service receipt queries systemd after unit exit, when the transient resource properties had been cleared. The independent live observations record the effective values while the worker ran. The process RSS metric reached 547,152 KiB and includes mapped shared pages. The cgroup figures measure memory charged to the service. [Live cap evidence](cap-observation.json) · [Bound samples](cap-physical-samples.jsonl.gz) · [Service receipt](memory-cap.json)

[Both calibration charts](charts/index.html)

## Reproduce

```sh
.venv/bin/python -B -m tools.pipeline_eval.qualification.recovery_reads_trial seal
nice -n 10 taskset -c 14 .venv/bin/python -B -m tools.pipeline_eval.qualification.recovery_reads_trial replay
nice -n 10 taskset -c 14 .venv/bin/python -B -m tools.pipeline_eval.qualification.recovery_reads_trial cap
.venv/bin/python -B -m tools.pipeline_eval.qualification.recovery_reads_trial publish
.venv/bin/python -m tools.pipeline_eval figures --panel screening --arm both \
  --evidence reports/2026_11_19_receiver_screening/deployment/recovery-reads \
  --out /tmp/recovery-reads-figures
.venv/bin/pytest -q tests/pipeline_eval/test_v5_recovery_reads.py
```

Use a fresh local `--runs` directory and a Linux user systemd manager with the memory controller. The recorded preflight import error occurred before the solver loaded. [Preflight source lock](preflight-source-lock.json) · [Source lock](source-lock.json) · [Prediction lock](prediction-lock.json)
