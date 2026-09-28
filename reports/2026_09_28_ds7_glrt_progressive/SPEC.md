# Sparse and progressive GLRT experiment

Frozen before new method timing on 2026-09-28. Research implementations only; no production changes or RF activity.

Reuse the preceding benchmark's hash-bound 28 saved DS7 dual-RX 120 ms visits: 16 at 2.5 MS/s and four at each of 5, 7.5, and 10 MS/s. This cohort has already been screened and is development data. No population recovery or holdout claim is permitted.

Run fresh original and exact-optimized baselines alongside eight new methods. Original means the same two SHA-pinned historical acquisition/scoring modules as the preceding experiment; other scientific dependencies remain current and are sealed before execution.

| Method | Probe indices (10 ms stride) | Candidates per probe |
|---|---|---:|
| candidates4 | 0 through 10 | 4 |
| candidates6 | 0 through 10 | 6 |
| windows6 | 0,2,4,6,8,10 | 8 |
| windows4 | 0,3,6,9 | 8 |
| windows3 | 0,5,10 | 8 |
| windows6_candidates2 | 0,2,4,6,8,10 | 2 |
| windows4_candidates2 | 0,3,6,9 | 2 |
| progressive4 | Start 0,3,6,9; expand remaining indices for each unconfirmed RX | 8 |

Progressive search uses only freshly computed evidence within the same dwell. It first completes the four initial windows on both receivers, then evaluates remaining windows in index order only for receivers still lacking a same-RX positive pair separated by at least 20 ms and within 8 kHz tracking CFO. Each receiver stops expanding after confirmation. Already computed probes are reused. Final folding is chronological and uses real indices/timestamps, not execution order. This is a detection-oriented approximation, not a full evidence replacement. No acquisition-once/direct-verification or native-kernel optimization is claimed by this experiment.

One CPU core (0), numerical threads fixed to one, two chronological repeats, method order rotated across visits/repeats. Per-call CPU and elapsed time include CI16 conversion and every executed search/score/fold; exclude file reads, hashing, and serialization. Each experiment has a 2400 second wall deadline. Failed calls and terminal errors remain in receipts. Inputs and all directly used scientific Python/native sources are hash-sealed. No concurrent DSP benchmark is intentionally run.

Use frozen prior scoring: one-to-one candidate identity association within 2 us and 8 kHz; separate positive-only matching; fresh confirmation on separated probes. Count science on repeat zero only. Report CPU/elapsed time, exact full-output equality, positive hypothesis and RX/probe recovery, identity-matched confirmation recovery, added positives, and score/CFO deltas. The 90%/80% gates apply to confirmation recovery separately for each rate; also expose the much lower hypothesis coverage of sparse methods. Original nonconfirming RX/visits remain available to report added confirmations relative to the original, without interpreting them as physical false alarms.

Baseline equality to prior saved original results, replay repeatability, method-owned tests, and independent evaluator checks are required before reporting success. Rank configurations by measured CPU cost subject to the requested recovery gate. Do not discard weak rates, slow fallback cases, or failures.
