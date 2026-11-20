# Prepared fractional detector on two complete IQ replays

The prepared fractional kernel kept every ordinary native call and reproduced both stock cavity positions and Doppler RMS values exactly on both recordings. It shortened full measured saved-IQ-to-position wall time by **11.723 s on DS26** and **7.438 s on DS29**, or **6.3%** and **5.7%**. Each service peaked at **536,870,912 bytes** of cgroup memory with zero swap and zero OOM. [Full-factor and position comparison](comparison.json) · [Position charts](plots/README.md) · [Full-visit stock controls](../whole-pair/README.md)

## ABI, acquisition and factor parity

The stock and candidate binaries use ABI 1 and identify as `wave8-gate314-source-v1`. Both actual installed acquisition releases independently ran their original wrapper with each binary on an archived dual-receiver, 10 MS/s, 20 ms canary. Within each release their ABI capability vectors and complete canary payloads matched exactly. The build and binary SHA, wrapper source SHA and preflight results are bound by the source lock. [Installed-wrapper preflight](abi-preflight.json) · [Source and input lock](source-lock.json)

The full raw replay covered all 6,769 saved DS26 visits and all 6,772 saved DS29 visits. Every visit record matched stock literally. All 14 segment receipts per recording matched after excluding measured stage timings and the detector binary SHA. The complete candidate input matched the stock native SHA after normalizing only the detector digest, analysis digest and derived run ID. The actual newly emitted candidate digest stays in the factor file and its blind position request. The original per-case catalogue, tile and truth-free settings matched. [Complete lane, factor and request receipts](stages.json.gz) · [Prediction lock](prediction-lock.json)

## Full replay cost

| Measured stage | DS26 stock → prepared | DS29 stock → prepared |
|---|---:|---:|
| Recorded acquisition span (s) | 299.996 | 300.018 |
| Raw authentication, decoding and GLRT wall (s) | 117.220 → 100.916 | 88.071 → 78.995 |
| Raw cgroup CPU (s) | 218.539 → 186.646 | 163.959 → 147.968 |
| Cavity position wall (s) | 67.961 → 71.161 | 41.218 → 41.612 |
| Full wall to both positions (s) | **186.319 → 174.595** | **130.225 → 122.787** |
| Full cgroup CPU (s) | 287.278 → 259.153 | 205.571 → 190.671 |
| Full wall / recorded span | 0.621 → 0.582 | 0.434 → 0.409 |
| Position process peak RSS (KiB) | 467,768 → 467,948 | 479,256 → 478,160 |

Each independent service used CPUs 18 and 19, one numerical thread per raw lane, and nice 10. The same process replaced the orchestrator with the original cavity worker on CPU 18 inside that service. Candidate assembly and parity checks took 2.346 s in DS26 and 2.006 s in DS29. Systemd service lifetimes were 175.782 and 123.771 s. Full times include candidate validation. Stock timing comes from the earlier full-visit runs with the same affinity and cap on a shared host. [Stage and physical cgroup counters](stages.json.gz)

## Individual detector calls

| Recording and detector | Valid calls | Wall mean / median / p95 (ms) | CPU mean (ms) | At most 20 ms |
|---|---:|---:|---:|---:|
| DS26 stock | 6,765 | 27.404 / 27.252 / 33.360 | 27.263 | 86 |
| DS26 prepared | 6,765 | 22.393 / 22.129 / 28.479 | 22.238 | 1,650 |
| DS29 stock | 4,868 | 26.880 / 26.556 / 32.690 | 26.527 | 44 |
| DS29 prepared | 4,868 | 22.815 / 22.460 / 28.350 | 22.627 | 861 |

The measured native-call wall improvement increased the number of individual calls within 20 ms. Most calls still exceeded 20 ms. The full host replays finished in less than the saved acquisition spans. [Per-visit timings](comparison.json)

## Matched outputs

| Recording | Arm | Position error (km) | Conditional Doppler RMS (Hz) |
|---|---|---:|---:|
| DS26-0036 | `c = 0` | 0.218118 | 102.253327 |
| DS26-0036 | Fitted `c` | 0.180112 | 102.288908 |
| DS29-0082 | `c = 0` | 2.789469 | 106.672251 |
| DS29-0082 | Fitted `c` | 2.654183 | 106.588481 |

Each table entry is identical between stock and prepared. The positions are the cavity endpoints on ordinary factors. The original v5 choices in the charts use capture-era factors. [Per-arm scores](scores.csv) · [Exact prediction records](positions.jsonl.gz)

## Reproduce

```sh
.venv/bin/python -B -m tools.pipeline_eval.qualification.whole_fractional seal
.venv/bin/python -B -m tools.pipeline_eval.qualification.whole_fractional run --case DS29-0082
.venv/bin/python -B -m tools.pipeline_eval.qualification.whole_fractional run --case DS26-0036
.venv/bin/python -B -m tools.pipeline_eval.qualification.whole_fractional publish
.venv/bin/python -m tools.pipeline_eval figures --panel screening --arm both \
  --evidence reports/2026_11_19_receiver_screening/streamlined/whole-fractional \
  --out /tmp/whole-fractional-figures
.venv/bin/pytest -q tests/pipeline_eval/test_whole_fractional.py
```

Use a fresh `--runs` directory, the exact builder artefact and local read-only archive identity, and the Linux user systemd memory controller. [Protocol](PROTOCOL.md)
