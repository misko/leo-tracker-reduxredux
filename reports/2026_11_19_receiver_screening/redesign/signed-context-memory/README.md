# Sampled causal phase widths through signed context

The signed-width worker reproduced the two-change control's complete positions, conditional radio fits and scientific decisions on the same authenticated ordinary DS29-0082 factors. Peak process RSS fell from **817,572 to 582,508 KiB**. Under a true **512 MiB** cgroup limit and zero swap, the worker completed signed context and was OOM-killed during family nomination. It returned no position in either calibration arm. [Exact comparison](comparison.json) · [Cgroup stage trace](memory-cap.json) · [Position charts](plots/README.md)

The frozen signed stage uses the phase widths and their receipts. The previous bank also constructed a padded orbit grid used by callers that need arbitrary prior epochs. The new route applies the same three-sample alignment reader already checked in family confidence to the signed width calls alone. It preserves the original per-satellite receipt calculations, signed qualification, paired RF fit, and downstream policies. [Protocol](PROTOCOL.md) · [Signed-context extension](../../../../tools/pipeline_eval/variants/v5_signed_context_memory.py) · [Family-width evidence](../family-memory/README.md)

| Measurement | Two-change control | Sampled signed widths |
|---|---:|---:|
| Native preparation cumulative peak RSS (KiB) | 496,428 | 496,692 |
| Ranked discovery cumulative peak RSS (KiB) | 511,488 | 525,472 |
| Family confidence cumulative peak RSS (KiB) | 511,488 | 525,472 |
| Peak RSS at family nomination entry (KiB) | 817,572 | 525,472 |
| Peak RSS at family nomination return (KiB) | 817,572 | 582,508 |
| Complete process peak RSS (KiB) | 817,572 | 582,508 |
| Whole worker CPU / wall (s) | 109.69 / 125.44 | 121.02 / 164.30 |
| Late temporary bank writes (bytes) | 613,672,128 | 613,672,128 |
| Blocking call at 512 MiB | Signed context | Family nomination |

The unrestricted signed call took 1.052 CPU seconds. Its live RSS moved from 501,512 to 501,516 KiB and it returned at the same 525,472 KiB process peak as entry. Family nomination raised that peak by 57,036 KiB. The concurrent host workload varied across the trials. Both numerical processes ran on CPU 17 at nice value 10. The cap reached exactly 536,870,912 cgroup bytes with zero swap after 45.955 service wall seconds and 44.961 CPU seconds. The signed change adds zero temporary writes, and the capped run stopped before late scratch creation. [Unrestricted receipt](uncapped-positions.jsonl.gz) · [Control receipt](control-positions.jsonl.gz) · [Capped result](capped-positions.jsonl.gz)

Both complete runs gave 2.784 km geographic error at `c = 0` and 2.651 km with fitted `c`. Conditional Doppler RMS was 106.670 and 106.587 Hz, respectively, with 1,310 associated observations in each arm. Geography was joined after the prediction lock. This is a one-recording host replay. [Per-arm scores](scores.csv) · [Source lock](source-lock.json) · [Prediction lock](prediction-lock.json)

## Reproduce

```sh
.venv/bin/python -B -m tools.pipeline_eval.qualification.signed_context_memory_trial seal
nice -n 10 taskset -c 17 .venv/bin/python -B -m tools.pipeline_eval.qualification.signed_context_memory_trial replay
nice -n 10 taskset -c 17 .venv/bin/python -B -m tools.pipeline_eval.qualification.signed_context_memory_trial cap
.venv/bin/python -B -m tools.pipeline_eval.qualification.signed_context_memory_trial publish
.venv/bin/python -m tools.pipeline_eval figures --panel screening --arm both \
  --evidence reports/2026_11_19_receiver_screening/redesign/signed-context-memory \
  --out /tmp/signed-context-memory-figures
.venv/bin/pytest -q tests/pipeline_eval/test_v5_signed_context_memory.py
```

Use a fresh `--runs` directory and a Linux user systemd manager with memory control.
