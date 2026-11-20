# Row-bounded complete-family nomination

The tiled worker matched the complete dense family nominations and both unrestricted positions exactly on authenticated ordinary DS29-0082. Under **512 MiB with zero swap**, it finished all 15 family nominations and was OOM-killed inside the first streamed state-bank write for residual screening. It returned no capped position. The previous signed-context worker stopped inside family nomination. [Exact nomination comparison](nomination-parity.json) · [Cgroup trace](memory-cap.json) · [Position charts](plots/README.md)

The original scorer still examines every one of 1,680 regional satellites per family. It receives the same family data, covariance and FP64 projection in 64-row tiles. The concatenated raw scores, alias arrays, phase coordinates, minimum elevations and full native `argsort` all match the dense run bitwise. Refined candidate scores, associated observations, and complete nominations also matched. The maximum simultaneously retained projection output payload fell from 18,816,000 to 573,440 bytes. This measures returned projection arrays. Interpolation and the correlated solve also have temporary working buffers. [Worker source](../../../../tools/pipeline_eval/variants/v5_nomination_memory.py) · [Fresh dense receipt](fresh-control-positions.jsonl.gz) · [Unrestricted candidate](uncapped-positions.jsonl.gz)

| Measurement | Fresh dense | Tiled |
|---|---:|---:|
| Nomination-entry cumulative peak RSS (KiB) | 532,480 | 532,520 |
| Nomination-return cumulative peak RSS (KiB) | 585,748 | 532,520 |
| Nomination-return live RSS (KiB) | 537,232 | 509,596 |
| Complete peak process RSS (KiB) | 585,748 | 549,152 |
| Nomination CPU / wall (s) | 5.44 / 5.48 | 4.34 / 4.46 |
| Complete worker CPU / wall (s) | 97.23 / 98.29 | 97.54 / 101.07 |
| Complete late scratch writes (bytes) | 613,672,128 | 613,672,128 |

The dense control ran on CPU 18 and the candidate on CPU 17, both at nice 10. The archived signed-context worker peaked at 582,508 KiB. The capped tiled worker reached 536,866,816 cgroup bytes, one 4 KiB page below its maximum. Systemd recorded zero swap, 55.482 CPU seconds and 58.775 service wall seconds. The last marker was entry to `late.stream_states#1` within `screen_candidates`. The sampled cgroup showed approximately 464.4 MB anonymous memory before entry and 69.8 MB file charge just after the worker exited. These samples motivated a separate writeback and cache eviction trial. [Archived signed-context control](../../redesign/signed-context-memory/README.md) · [Live cgroup samples](live-cgroup-samples.txt) · [Scratch-cache trial](../recovery-cache-memory/PROTOCOL.md)

Both complete unrestricted workers gave 2.784 km horizontal error at `c = 0` and 2.651 km with fitted `c`. Their separate conditional Doppler RMS values were 106.670 and 106.587 Hz, respectively, over 1,310 associated observations in each arm. Geographic scoring followed prediction sealing. [Per-arm scores](scores.csv) · [Source lock](source-lock.json) · [Prediction lock](prediction-lock.json)

## Reproduce

```sh
.venv/bin/python -B -m tools.pipeline_eval.qualification.nomination_memory_trial seal
nice -n 10 taskset -c 17 .venv/bin/python -B -m tools.pipeline_eval.qualification.nomination_memory_trial replay
nice -n 10 taskset -c 18 .venv/bin/python -B -m tools.pipeline_eval.qualification.nomination_memory_trial stock
nice -n 10 taskset -c 17 .venv/bin/python -B -m tools.pipeline_eval.qualification.nomination_memory_trial cap
.venv/bin/python -B -m tools.pipeline_eval.qualification.nomination_memory_trial publish
.venv/bin/python -m tools.pipeline_eval figures --panel screening --arm both \
  --evidence reports/2026_11_19_receiver_screening/deployment/nomination-memory \
  --out /tmp/nomination-memory-figures
.venv/bin/pytest -q tests/pipeline_eval/test_v5_nomination_memory.py
```

Use a fresh `--runs` directory and a Linux user systemd manager with the memory controller. All results are host measurements for one recording. [Protocol](PROTOCOL.md)
