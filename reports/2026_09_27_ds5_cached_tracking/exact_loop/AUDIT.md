# Exact-loop optimization audit

## Decision

Stop before a **server prototype** and before the proposed 256-visit plus
24-control paired replay. The material CI16 loops that looked scalar in the
measured x86 FFTW build already have exact ARM NEON implementations. The only
uncovered ARM loop is selected-window packing. Historical x86 server timings
show that a server implementation of that isolated change cannot meet the
frozen 10% projection gate at either rate.

This is a read-only, hash-pinned audit. It did not build a candidate, consume a
DSP timing slot, open holdout IQ, alter a detector statistic, or measure ARM
performance. The server projection is not a bound on physical ARM packing
cost; that cost remains unknown and needs hardware measurement.

## Source findings

The FP32 FFTW bridge already compiles double-to-float and float-to-double copies
as packed SSE conversions. The build already uses `-fcx-limited-range`.
Remaining integer division/modulo instructions are in sparse proposal and epoch
bookkeeping rather than dense visit loops. Replacing them cannot materially
change whole-call cost. The final GLRT intentionally retains libc `cabs` for
its ceilings, so replacing that helper would change qualified numerical
semantics.

The exact CI16 arithmetic needed by ARM is already present:

- Sample-aligned dual-RX rank uses `vld4_s16`, `vmull_s16`, widens each int32
  product with `vmovl_s32`, then adds/subtracts in int64 lanes. This avoids the
  CI16-extrema overflow that a packed int32 complex multiply would introduce.
- Selected-window coarse power/differential folding uses the same per-product
  widening and int64 accumulation through `coarse_fold_ci16`.
- Stationary-tone nuisance energy and three lag probes use `vld2_s16`,
  `vmull_s16`, and `vpadalq_s32` into int64 lanes.

The frozen Cortex-A9 cross-compile receipt verifies the aligned rank helper
contains `vld4.16`, `vmull.s16`, `vmovl.s32`, `vadd.i64`, and `vsub.i64`. It is
disassembly evidence only and does not support an ARM speed claim.

## Materiality bound

The selected-window natural-stride-to-packed loop remains scalar on ARM. Its
time is inside dwell orchestration and has no dedicated timer. For each of the
16 fixed receiver visits per rate in the frozen **x86_64 server** cost receipt,
the audit formed:

`dwell total - rank total - confirmation total`

On that server, this residual includes packing, orchestration, and timer
non-additivity, so the largest positive residual is a conservative observed
upper bound on server savings from packing alone. It provides no corresponding
upper bound for ARM.

| Rate | dwell median | residual median | largest positive residual | 10% gate | perfect-removal / gate |
|---|---:|---:|---:|---:|---:|
| 2.5 Msps | 0.970930 ms | 0.001767 ms | 0.007482 ms | 0.097093 ms | 0.0771 |
| 5 Msps | 2.055469 ms | 0.006373 ms | 0.040582 ms | 0.205547 ms | 0.1974 |

Even deleting packing and the positive residual entirely would deliver less
than one fifth of the required projected server saving. An SSE implementation
of the rank/coarse loops could improve this x86 server, but it would duplicate
the existing ARM NEON paths and would not answer the user's hardware goal. The
server projection gate therefore ends this prototype branch without code or
scientific replay. Whether NEON packing matters on the physical ARM target is
still an open measurement question.

Machine-readable evidence and source hashes are in `evidence.json`.
