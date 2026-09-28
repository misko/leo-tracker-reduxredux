# Four-epoch, one-CFO ARM coarse kernel

This bounded experiment changes only the unit-stride bulk path of the FP32
coarse search. Each NEON vector contains four adjacent epochs. The outer loop
visits one CFO at a time, so the tap loop has only two live accumulation
vectors (`r` and `i`). `vld2q_f32` gathers the four overlapping IQ samples and
the real and imaginary template scalars are broadcast. The multiply, inner
add/subtract, and running-add grouping matches the original kernel for every
epoch/CFO hypothesis. Magnitude uses the same zero guard and two reciprocal
square-root refinements. Results are scattered to the unchanged epoch-major
accumulator layout.

The four scalar denominators and support counts retain their original order.
Sparse-cell refinement still uses the original scalar kernel. Non-unit epoch
strides and the final zero-to-three epochs use the original scalar path. No
frequency, symbol, frame, window, or hypothesis is dropped.

Host qualification used the latest conditioned-CZT host build as its oracle.
The pure kernel is byte-exact for tap counts 1, 2, 3, 4, 11, 17, 22, 33, 44,
and 45, including zero inverse-normalization lanes. Full coarse grids are
byte-exact at 2.5, 5, 7.5, and 10 MS/s for full 20 ms windows and partial
`2*n+17` inputs; zero IQ produces the same all-zero grids. This stronger direct
grid comparison makes another 64-file host cohort unnecessary for kernel
qualification.

The ARM disassembly in `arm_kernel.asm` confirms the intended loop shape: one
`vld2.32`, two vector accumulators, scalar coefficient broadcasts, and no
vector spills in the tap loop. The exact-kernel test also passes on ARM
hardware.

## Measured decision

Reject this kernel. Across the bounded four-probe, three-repetition hardware
comparison, it averages 1,746.50 ms/window versus 1,559.84 ms/window for the
current conditioned-CZT baseline, about 12% slower. Because that result is
decisive, the 704-dwell cohort and additional all-rate hardware runs were not
started.

Builds:

- ARM: `/var/tmp/leo-arm-epoch-lane-v1`
- Host: `/var/tmp/leo-host-epoch-lane-v1`

Both build receipts identify the baseline receipt, compiler commands, every
source hash, and output binary hashes. The coarse header retains its scoped
`no-prefetch-loop-arrays` pragma from the latest baseline.
