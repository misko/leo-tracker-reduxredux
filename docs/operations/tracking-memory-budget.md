# Tracking memory and queue balance

The October 5, 2026 trial uses 18 signal-analysis (`heavy`) leases and four
tracking (`memory`) leases, with 23 worker services. The extra service can wait
for capacity. Keep the database lease limits authoritative; worker count alone
does not describe analysis concurrency. Each tracking job can also fork four
position-scoring children.

Before the trial, the host had 81 GiB available of 122 GiB, negligible current
swap traffic, and 98–99% CPU utilization. Earlier tracking cgroups used
12–17 GiB each, mostly mapped file pages; anonymous memory was about 3–4 GiB.
Summing child RSS substantially overstates shared memory. Four tracking slots
are a bounded trial, not evidence that a further increase is safe or faster.

## Memory changes

Candidate scoring now computes residuals in batches of 32, keeping float64
arithmetic, the same observation masks, tau selection, and candidate tie breaks.
Only the small candidate-by-tau score tables span the full candidate set.

Prediction-bank construction propagates 128 candidates at a time into mapped
arrays through allocation/finalization ports. It retains the full coarse
validity window and the original candidate order and filtering. Finalization
reopens each bank read-only before position workers share it. Scratch mappings
are closed and their temporary directory is removed on success or exception.
The concrete filesystem adapter remains outside the numerical analyzer.

## Validation

37 component tests cover scoring parity, cross-batch ties, invisible candidates,
noncontiguous float32/float64 inputs, invalid orbital candidates, allocation
ports, mapping cleanup, CLI completion checks, storage and persisted contracts.
No scientific fixture or persisted configuration changed.

Separate-process benchmarks compared the deployed lease-fix overlay against
the new implementation, with one BLAS thread per process:

| Measurement | Previous | Batched |
|---|---:|---:|
| Scoring peak RSS, 256 candidates × 11 taus × 4,000 observations | 505 MiB | 255 MiB |
| Scoring mean CPU time, five evaluations | 0.779 s | 0.183 s |
| Real-input bank replay peak RSS | 473 MiB | 363 MiB |
| Real-input bank replay wall time, including preparation | 28.6 s | 17.7 s |

The bank replay used session `scan-fw-cc609ed603589e6e`, its first two eligible
tracks (at most 128 observations each), and the first 1,024 original candidate
indices. All candidate, position, velocity, and coarse-bank hashes matched
exactly, as did receipt counts. The scoring result also matched exactly.
These are bounded stage measurements, not whole-job savings or localization
accuracy improvements. Timings on the busy production host are indicative.

Raw evidence and the reproducible benchmark script are retained under
`/home/mouse9911/release-evidence/tracking-memory-batches/`.

## Deployment and rollback

Preserve the complete deployed lease-fix overlay and replace only the two
analysis modules, the TLE-position CLI, and `storage/prediction_scratch.py`.
Do not deploy a bare main checkout over the other active production overlays.
Drain existing jobs before restarting their worker services, then restore
18/4 admission and verify fresh leases and the source path in every worker.

Rollback restores `PYTHONPATH=/opt/leo-adaptive-lease/64226778c/src`. If the
concurrency trial shows CPU contention or memory pressure, restore heavy=20
and memory=3 under the processing-resource advisory locks. Do not reclaim a
live job merely because its worker is being upgraded.
