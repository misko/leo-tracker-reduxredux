# Integrated F(4,3) regional coarse experiment

This isolated variant starts from Wave7 float-final V2, so its fair whole-run
control is the measured float-final V2 result (856.661454 ms ARM4), not plain
Wave6. The only new arithmetic is the regional FP32 coarse correlation.

For each run of four consecutive selected epochs, every three-tap template
chunk uses rational Winograd F(4,3). Its six-sample input transform is shared
across the 12 CFOs, transformed templates are cached when the workspace is
created, and ARM evaluates CFO lanes four at a time with explicit NEON. The
fifth epoch of a radius-two region, nonconsecutive epochs, incomplete tap
chunks, and boundary-limited support remain on direct scalar/tail handling.
All frames, symbols, CFOs, selected epochs, and support checks are retained.

The actual direct coarse implementation and the fair standalone comparator
both accumulate each CFO lane in increasing tap order. Winograd is
algebraically equivalent but changes FP32 reduction order, so this is an
explicit approximation. The fair CPU0-pinned Cortex-A9 microbenchmark measured
909.655 ms versus 1519.452 ms for an equally packed explicit-NEON direct
kernel, ratio 0.5993. That result motivates integration but does not predict a
40% full-pipeline improvement.

The owned component test compares the integrated grouped path against the
actual direct coarse primitive at all four rates, on zero and random inputs,
with fifth-epoch handling and 11/22/33/44 active-support lengths. Host and
sanitizer units pass; ARM cross-builds with warnings as errors. Host32 retains
834/843 frozen positive hits. Host704 retains 19,217/19,581 with zero lost or
gained hit identities relative to float-final V2. Host runtime is not useful
for speed qualification because its Winograd branch is scalar.

The host cohorts were produced before a receipt-only metadata correction; they
bind the same source and binary hashes. The final receipt now explicitly names
the float-final V2 base. Final ARM runner SHA-256 is
`06eb2553d86c1427c3408111076bcf3c33273358936a7b05e45010daf5678a57`;
receipt SHA-256 is
`9d43d83f26c9b558f491a8d6f168cb6de81f7f5228844269e4f3699bbf472ee2`;
the ARM component unit is
`6886edf40c964331c40de493db5eb44748b4d3b755af669bc5a83f939574abca`.

## Physical result and bounded V2 fix

Integrated V1 is rejected. Root's ARM4 run measured 974.934986 ms total versus
856.661454 ms for float-final V2, while coarse time rose from about 134 ms to
257.883603 ms. Units passed. The host704 identity audit nevertheless found
19,217 matched hits on both sides, with zero lost and zero gained identities.

Disassembly explains why the standalone result did not transfer. V1's
integrated helper has a 756-byte stack frame, 175 stack references, and 245
scalar VFP loads/stores. It materializes four-by-twelve complex partial outputs
after every three-tap chunk and computes the final 48 magnitudes with scalar
`sqrtf`; the real direct coarse kernel uses packed NEON magnitude/reciprocal
square root. The one-chunk microbenchmark did not exercise this accumulation
and magnitude cost.

A single bounded fix is isolated in `sources-v2` and `builds-v2`: keep four
epoch accumulators live per four-CFO group and use the baseline vector
`coarse_magnitude` for all final lanes. Host and sanitizer units pass. The V2
ARM runner SHA-256 is
`8272ff30cf47eceec38d8d8e2c651bdef5fca7f1aaeed29b018ec68c8d175588`;
unit SHA-256 is
`41cdff69982149e4be39a061edf935589379ded65df153d49737bd68ecccf40d`.

The physical V2 result also rejects the approach: 1004.373795 ms total and
287.538837 ms coarse, versus 856.661454 ms total and about 134 ms coarse for
float-final V2. It retained 119 hits and emitted the same 182 objects on the
matched ARM4 panel. The fresh receipt-bound V2 host704 cohort retains
19,217/19,581, with 0 lost and 0 gained matched hit identities. Reducing the
pointwise complex multiplication count did not repay the full-symbol transform,
register-pressure, spill, output-transform, and accumulation costs on this
Cortex-A9 implementation. Both V1 and V2 are sealed negative results; no
further Winograd variants are qualified.

The exact V1 `coarse_fp32.h` measured by the V1 cohort receipts is archived at
`sources-measured-v1/src/native_presence/coarse_fp32.h`. Its SHA-256 is
`4410d1d2da4c0a8457b6c46c982202fa2e884939b55487cb470a01c6c3ab015c`,
matching the immutable ARM4, host32, and host704 receipts. This repairs source
availability only; none of those receipts or measured outputs was changed.

Rebuild with:

```sh
python3 reports/2026_09_29_arm_wave7_coarse_winograd_integrated/build.py
```
