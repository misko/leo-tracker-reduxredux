# Held complete ordinary IQ replays

Both held five-minute recordings completed from saved IQ to both position estimates inside an enforced 512 MiB host cgroup with zero swap. Every ordinary detector visit matched the archived stock output, and both positions and conditional Doppler RMS values matched a fresh stock-factor cavity control exactly. The detector exceeded the individual 20 ms deadline on most analyzed visits. All four complete optimized replays to date come from the same roof. [Data and source hashes](prediction-lock.json) · [Earlier complete replays](../../streamlined/whole-fractional/README.md)

## Selection and controls

The prospective roster contained six authenticated ordinary saved-IQ recordings. After excluding the two development recordings DS26-0036 and DS29-0082, the lowest SHA-256 rank within each dataset selected DS26-0237 and DS29-0174. DS26-0122 and DS29-0247 ranked second and were excluded. No GPS outcomes or prior solver status entered selection. Source and input locks bind the original capture manifests, ordinary factor documents and requests, and the exact ABI 1/wave8 prepared-fractional detector. [Protocol](PROTOCOL.md) · [Roster and exclusions](cohort.json) · [Source and input lock](source-lock.json)

Each fresh stock-factor control read the authenticated archived full ordinary factors and ran the same compact cavity on CPU 18. The complete candidate decoded every available saved-IQ visit with two single-threaded lanes pinned to CPUs 18 and 19, then ran the same cavity on CPU 18. All services used nice 10 and the independent enforced cap of 536,870,912 bytes with zero permitted swap. The factor-only controls had a 100 second deadline and the complete replays a 300 second deadline. All four services exited successfully on the first attempt. [Stage and cgroup receipts](stages.json.gz)

## Position and conditional Doppler fit

The matched stock-factor control and complete optimized replay produced the same coordinates and conditional Doppler RMS for each arm. The candidate request preserved the original ordinary settings after accounting for provenance and the new pathname. [Positions](positions.jsonl.gz) · [Matched controls](control-positions.jsonl.gz) · [Checked geographic scores](scores.csv)

| Recording | Arm | Latitude | Longitude | Geographic error (km) | Conditional Doppler RMS (Hz) |
| --- | --- | ---: | ---: | ---: | ---: |
| DS26-0237 | `c = 0` | 37.84986737 | −122.49581923 | 0.889 | 110.246 |
| DS26-0237 | Fitted `c` | 37.85018872 | −122.49491410 | 0.814 | 110.117 |
| DS29-0174 | `c = 0` | 37.85201083 | −122.49843288 | 1.161 | 113.047 |
| DS29-0174 | Fitted `c` | 37.85208553 | −122.49915529 | 1.224 | 113.147 |

The fitted arm had lower error and lower conditional Doppler RMS on DS26-0237, with both higher on DS29-0174. The original v5 capture-era factor comparisons use a different native input and have their own results. [Capture-era v5 modes](capture-era-v5.csv) · [Score lock](score-lock.json) · [Both-arm figure manifest](plots/manifest.json)

## Replay resources

The intervals use monotonic stage times and differences in aggregate cgroup CPU usage. Stock factor-to-result includes opening and authenticating the archived factors. Optimized raw includes lane decoding and detector calls. Raw plus assembly includes auditing every visit and binding the new native document to the frozen request. Whole replay starts before saved IQ is read and ends with both arm results. [Raw and timing comparisons](comparison.json) · [Stage and cgroup receipts](stages.json.gz)

| Boundary | DS26 wall (s) | DS26 CPU (s) | DS29 wall (s) | DS29 CPU (s) |
| --- | ---: | ---: | ---: | ---: |
| Fresh stock factor to result | 88.592 | 87.579 | 76.075 | 75.352 |
| Optimized raw | 100.710 | 184.953 | 102.882 | 188.816 |
| Optimized raw plus assembly | 103.162 | 187.394 | 105.707 | 191.458 |
| Optimized cavity | 86.530 | 85.865 | 72.991 | 72.808 |
| Optimized whole saved IQ to result | 189.856 | 273.423 | 178.877 | 264.443 |
| Original acquisition span | 299.997 | — | 300.028 | — |

Both complete services reached 512 MiB cgroup peak. Position process peaks were 523,984 and 493,892 KiB. The stock factor-only services reached 512.00 and 475.85 MiB, respectively. All four cgroups reported zero swap and zero OOM events. The complete replay was shorter than the recorded acquisition span on both recordings. The host test used two replay CPUs and saved input, so it does not establish a single-visit or embedded target deadline. [Stage and cgroup receipts](stages.json.gz)

| Recording | All visits audited | Ordinary RX probe rows | Excluded visits | Calls ≤20 ms / analyzed calls | Analyze wall mean / median / p95 (ms) |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS26-0237 | 6,768 | 13,532 | 2 | 1,657 / 6,766 | 22.347 / 22.096 / 28.274 |
| DS29-0174 | 6,774 | 13,408 | 70 | 1,271 / 6,704 | 23.031 / 22.537 / 29.387 |

Every visit line, including acquisition exclusions and rejected detector content, matched the archived ordinary stock detector. All 14 segment records per recording matched after excluding library identity and timing. The candidate factor documents preserve the actual optimized detector identity. Normalizing the documented lineage fields reproduced the full authenticated ordinary factor digest, including both RX rows. [Raw and timing comparisons](comparison.json)

The earlier stock ordinary raw-plus-assembly replay took 178.428 s on DS26 and 222.756 s on DS29. Its original full pipeline took 353.127 s and 515.979 s respectively, with a different position path and historical execution conditions. A fresh stock saved-IQ replay was outside this held protocol. The matched fresh control supports numerical equivalence, while the archived timing has its own execution boundary. [Archived timing fields and boundaries](comparison.json)

## Reproduction

Use a new empty bulk directory in place of `<runs>`. The geographic exporter binds DS26 to `ds26-all159` and DS29 to `roof16` after sealing position records. The original inherited `publish` path joined only `roof16` and stopped on DS26-0237 after writing the numerical lock. The scoped exporter reproduced that lock and completed both geographic joins without replaying either service.

```sh
.venv/bin/python -m tools.pipeline_eval.qualification.full_held_pair seal --runs <runs>
.venv/bin/python -m tools.pipeline_eval.qualification.full_held_pair control --runs <runs> --case DS26-0237
.venv/bin/python -m tools.pipeline_eval.qualification.full_held_pair replay --runs <runs> --case DS26-0237
.venv/bin/python -m tools.pipeline_eval.qualification.full_held_pair control --runs <runs> --case DS29-0174
.venv/bin/python -m tools.pipeline_eval.qualification.full_held_pair replay --runs <runs> --case DS29-0174
.venv/bin/python -m tools.pipeline_eval.qualification.full_held_scores --runs <runs>
```
