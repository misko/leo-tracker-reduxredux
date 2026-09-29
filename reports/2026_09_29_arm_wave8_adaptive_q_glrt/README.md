# Wave 8 adaptive-Q int32 final-dot experiment

This isolated frontier variant retains proposal8, half-grid proposals,
tracking-min1, radius1, all final frames and symbols, and the downstream FP64
FFT/spectra/ceilings/scoring path. Only the final matched-filter dots are
quantized.

The experiment-private prepared-CI16 entry point borrows the original CI16
pointer and stride during the synchronous search and clears both immediately
after return. The original prepared API remains available as a fallback. The
fused runner requires every candidate-bearing call to report nonzero integer
dot calls and zero fallbacks.

Templates are initially quantized at Q11 relative to their measured maximum.
Symbols up to 11 taps retain Q11, up to 22 taps shift to Q10, and longer
symbols shift to Q9. The worst complex-component bound is
`2*taps*32768*qmax`: 1.476e9 for 11/Q11, 1.475e9 for 22/Q10, and 1.508e9 for
45/Q9, below signed int32 maximum. ARM uses `vmlal_s16`/`vmlsl_s16` and int32
horizontal reductions.

Host and sanitizer units pass across all rates, strides 2/4, extrema, score
tolerance, and residual-bin parity; ARM cross-builds with warnings as errors.
The final receipt-bound host704 cohort reports 144,273,920 adaptive-Q dot calls,
zero fallbacks, and `final_scorer: adaptive_q_int32` on every row. It recovers
18,465/19,581 frozen hits with 77,894 emitted candidates, and the identity audit
finds zero lost or gained hits versus the full-coarse radius1 frontier control.
Host timing is diagnostic and slightly slower: 60.648 ms fused versus 58.432
ms control.

ARM runner SHA-256 is
`fa067b5d42892aa55640affcec0ef58a890bb6a98f6021947162af9d3fde74fb`;
ARM unit SHA-256 is
`215d920a2828456a722da6e4aeeb5da83995f678239a9d0488200f6a7e3e74f9`;
receipt SHA-256 is
`05005a06e3fe6c626dbd0cdc541705813a3d3b0f9b65716a61fde1cb132ca49f`.
Root's matched physical ARM4 run rejects the variant for speed. It measured
521.845439 ms total versus 506.355 ms for the frontier control, while final
GLRT rose to 93.703 ms from 74.436 ms. Recovery remained 108/119, the ARM unit
passed, and runtime instrumentation recorded 315,264 adaptive-Q dot calls with
zero fallbacks. The integer kernel therefore executed as designed, but its
quantization, lane handling, reductions, and conversion costs outweighed the
replaced FP64 dots on Cortex-A9. No further adaptive-Q kernel variants are
qualified.

The earlier `host32-unlabeled-preinstrumentation` and
`host704-unlabeled-preinstrumentation` directories are quarantined historical
runs and are not qualification evidence.
