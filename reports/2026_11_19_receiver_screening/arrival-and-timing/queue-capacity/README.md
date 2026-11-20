# Detector queue capacity under matched load

At the preregistered 2.25× CPU scale, adaptive skipped the fifth-center calculation on about 37% of admitted visits and retained every valid visit on both recordings. Pure fifth dropped **64 of 6,761** valid visits on DS26-0197 and **74 of 6,774** on DS29-0316. Stock also retained every valid visit. Adaptive's fitted-c position was closer to truth than stock on both recordings. Pure fifth was more accurate on DS29 despite its higher loss. [Both calibration-arm position plots](charts/index.html) · [Queue sensitivity](queue-capacity.pdf)

## Modeled arrivals and completed packets

| Recording | Policy | Admitted | Dropped | Fifth-center calls | P95 completed age, ms |
|---|---|---:|---:|---:|---:|
| DS26-0197 | Stock | 6,761 | 0 | 0 | 41.95 |
| DS26-0197 | Adaptive | 6,761 | 0 | 4,280 | 49.84 |
| DS26-0197 | Fifth center | 6,697 | 64 | 6,697 | 81.61 |
| DS29-0316 | Stock | 6,774 | 0 | 0 | 42.60 |
| DS29-0316 | Adaptive | 6,774 | 0 | 4,267 | 50.17 |
| DS29-0316 | Fifth center | 6,700 | 74 | 6,700 | 82.43 |

The model holds arrival times fixed and scales each visit's previously measured native thread CPU. It applies the existing adaptive admission rule to a single worker with one waiting slot. The 11 hardware-invalid DS26 slots remain in the physical timeline and consume no service. The four pure 1× runs reproduce the historical CPU queue rows, including dropped visit IDs, completion totals, drain, wait and age summaries. At 2.5×, adaptive retained every valid visit while pure fifth dropped 602 and 622. At 3×, adaptive began dropping somewhat more than stock, at 369 versus 337 and 425 versus 391. The model omits scheduler stalls, decoder overhead, prefetch, other worker overhead and power effects. [Frozen protocol](PROTOCOL.md) · [All 42 modeled cells](queue-model.csv) · [Visit selections](queue-selections.json.gz) · [Historical parity](one-x-audit.json)

## Measured installed receiver fits

| Recording | Policy | c = 0 error, km | Fitted-c error, km | Fitted-c conditional RMS, Hz | Fit wall, s |
|---|---|---:|---:|---:|---:|
| DS26-0197 | Stock | 0.792 | 0.992 | 80.56 | 48.55 archived |
| DS26-0197 | Adaptive | 0.720 | 0.917 | 83.82 | 92.51 fresh |
| DS26-0197 | Fifth center | 1.020 | 1.205 | 85.40 | 86.23 fresh |
| DS29-0316 | Stock | 0.834 | 0.852 | 119.82 | 55.63 archived |
| DS29-0316 | Adaptive | 0.310 | 0.315 | 123.71 | 87.32 fresh |
| DS29-0316 | Fifth center | 0.231 | 0.235 | 120.88 | 118.40 fresh |

Both stock inputs exactly matched the complete prior native streams and reuse their sealed positions. The four fresh mixed or reduced inputs used the original installed phase-release backend on CPUs 10 and 11 at nice 10, with a 512 MiB cap and zero swap. All returned both calibration arms. Measured process-group fit CPU ranged from 84.58 to 106.67 seconds, and physical cgroup peak from 387.8 to 424.7 MiB. Archived stock wall came from the position stage of an earlier complete whole-IQ service. The four original v5 policy endpoints use capture-era inputs and happen to coincide within each recording and calibration arm. All DS26 policies exceeded the original v5 error by more than 10% in both arms. All DS29 policies met the 10% bound in both arms. [Per-arm position and RF results](position-scores.csv) · [All four original v5 records](capture-era-v5.csv) · [Prediction seal](prediction-lock.json)

Stock and adaptive retained identical visit support at 2.25×. The position difference comes from the changed detector packet mix. Adaptive's conditional RF residual increased on both recordings even as its position error fell relative to stock. The pure fifth branch changes both packet type and admitted visits. The scope is installed host fits on packets selected by modeled admission. [Source and cap proof](source-lock.json) · [Numerical and service receipts](positions.jsonl.gz)

Regenerate the score CSVs and sensitivity plots offline with `python -m tools.pipeline_eval.qualification.queue_capacity_results <output>`. Rebuild the standard both-arm book with `python -m tools.pipeline_eval figures --panel screening --variant queue-capacity-position --out <output>`.
