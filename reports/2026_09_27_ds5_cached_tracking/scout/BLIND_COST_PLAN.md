# Blind acquisition cost diagnostic

The common-profile blind path has no single 10x target. Receiver packing consumes
38--40% of measured server CPU, while native rank and confirmation consume the
rest. Within confirmation, coarse search is the largest aggregate stage at both
rates. Fractional scoring is almost as large at 2.5 MS/s, and fine acquisition is
the second-largest stage at 5 MS/s.

The measurement is a metadata-selected prefix: the first eight development visits
at each rate, both receivers, five repetitions after one warmup. It includes 16
receiver-visits per rate. Selection did not depend on detector output. The library
uses the hash-pinned common profile, and direct confirmation reruns were checked
for exact equality with the confirmation embedded in each dwell. No holdout data
or outcomes were opened. `blind_cost_receipt.json` has SHA256
`935d89bcdf39f3b8414ffa81f280feeb7e0a826e7c555133ccc16ff37785fd78`.

## Measured breakdown

The table uses sums of per-receiver medians so the stage totals remain additive.
Times are server thread/process CPU milliseconds across 16 receiver-visits.

| Stage | 2.5 MS/s | 5 MS/s | Share of relevant parent |
| --- | ---: | ---: | --- |
| Packing plus Python/native boundary outside dwell | 9.421 | 21.500 | 38.2%, 40.0% of outer call |
| Native dwell total | 15.229 | 32.214 | 61.8%, 60.0% of outer call |
| Rank total | 4.275 | 8.143 | 28.1%, 25.3% of dwell |
| Rank fold | 3.029 | 6.708 | 70.9%, 82.4% of rank |
| Rank correlation | 1.193 | 1.369 | 27.9%, 16.8% of rank |
| Confirmation total | 10.928 | 23.889 | 71.8%, 74.2% of dwell |
| CI16-to-complex conversion | 0.441 | 1.852 | 4.0%, 7.8% of confirmation |
| Tone nuisance | 0.704 | 1.677 | 6.4%, 7.0% of confirmation |
| Coarse search | 3.671 | 8.743 | 33.6%, 36.6% of confirmation |
| Fine acquisition | 2.193 | 6.316 | 20.1%, 26.4% of confirmation |
| Fractional timing and final score | 3.504 | 3.986 | 32.1%, 16.7% of confirmation |

The fine-stage profile attributes 1.112/2.575 ms to acquisition FFT work and
0.721/2.138 ms to conditioned CFO work at 2.5/5 MS/s. The fractional profile
attributes 1.092/1.477 ms to the five-cell epoch lattice and 2.394/2.513 ms to
the final full-support exact/control score. Local coarse refinement accounts for
0.414/1.861 ms.

Removing receiver packing entirely gives only 1.619x and 1.667x speedups. Even
removing an entire native stage gives modest ceilings: perfect removal of rank is
1.210x/1.179x, coarse 1.175x/1.194x, fine 1.098x/1.133x, and fractional
1.166x/1.080x. After packing is removed, native DSP would still need a 6.18x and
6.00x reduction to reach 10x at 2.5 and 5 MS/s. A one-stage optimization cannot
meet the goal.

## Exact-result work to try first

1. Add a native strided dual-receiver CI16 entry point. The current replay copies
   a complete 120 ms receiver before every blind call. A native ABI accepting the
   recorded `(sample, receiver, I/Q)` strides can fold each receiver directly or
   process both receivers in one traversal. Preserve every integer accumulation,
   hypothesis, ordering rule, and final FP operation. Require field-for-field
   equality of rank order, projected epochs, candidates, scores, and support flags
   against the common binary. This attacks the measured 38--40% outer overhead on
   every visit.
2. Optimize the rank fold, which is 71--82% of rank. The source already contains
   an exact widened-integer ARM NEON path; first confirm the production ARM build
   defines `__ARM_NEON` and measure it with the same stage counters. A dual-RX
   traversal can reuse template and index loads while keeping receiver sums
   independent. An x86-only SIMD result would not establish ARM benefit.
3. Fuse input traversals where operation order can remain identical. CI16 ingest,
   tone inspection, rank folding, and coarse preparation currently make separate
   passes. Sharing loads and precomputed indices is exact-result work; changing
   normalization order or floating summation order is not. Start with a cache and
   memory-traffic profile on ARM before changing arithmetic.
4. Run the two receiver workspaces concurrently if latency matters and two cores
   are available. This preserves results and can approach 2x wall-latency
   improvement, but it does not reduce total CPU and therefore must be reported
   separately from computational speedup.

## Changes that require numerical qualification

The common profile already enables FP32 coarse search, power and differential
proposals, iterative FFT, fast fine FFT, one candidate, CI16 differential work,
hybrid rank projection, amplitude weighting, bounded magnitude, and energy-based
support. Its ARM coarse kernel already has NEON code. Further hypothesis or
precision reductions are algorithm changes even if they look structurally safe.

The next bounded comparisons should each use the same fixed development prefix,
then the complete development split and synthetic controls. Promotion requires
all 36 reference positives, identical support/fractional-complete decisions,
identical margin decisions at the strict `> 0.025` boundary, and explicit score
drift bounds before one fresh holdout run.

- Feed the rank-projected epoch into seeded confirmation to bypass the full coarse
  timing search. This directly targets 34--37% of confirmation, but rank timing
  is only a proposal and must not be treated as exact without equality testing.
- Replace remaining FP64 acquisition FFT, conditioned-CFO, epoch-lattice, or final
  GLRT kernels with FP32/NEON kernels. Cortex-A9 NEON lacks general FP64 vector
  throughput, so these are plausible large wins, but rounding can change ordering
  and the margin boundary. Qualify each stage independently.
- Reduce coarse frames, anchor density, CFO cells, conditioned radius, epoch cells,
  or final support. These save work by removing evidence and are not
  exact-preserving. Test them only as separately named scientific variants.
- Compare the built-in FP64 FFT with a platform-tuned backend or an equivalent
  fixed-size kernel. Keep initialization outside capture. FFT output need not be
  bit-identical, so candidate ordering and final decisions require the same
  qualification as a precision change.

The failed sparse/rank screen means quiet visits cannot be skipped truthfully.
The immediate path is to remove transport and memory-copy work, verify the ARM
NEON paths actually run, and then qualify one acquisition-kernel change at a time.
