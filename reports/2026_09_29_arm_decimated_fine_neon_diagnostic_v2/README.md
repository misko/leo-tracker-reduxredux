# FP32 FIR forward-error qualification

The first ARM diagnostic failed the original scalar/NEON relative comparison
only for the cancellation-heavy alternating full-scale pattern.  At the first
NEON output, local input L1 was about 1.11 million while output magnitude was
25--43.  Pairwise errors were 0.000176--0.001229.  Zero, impulse, tone,
two-tone, out-of-band, and partial-length cases passed the original bound.

This v2 test retains that evidence and adds a double precision convolution
oracle built from the exact FP32 inputs, modulated coefficients, and oscillator
state.  It checks scalar and NEON results independently against a conservative
FP32 forward-error bound: `gamma(64)` times the componentwise weighted product
L1, plus `gamma(4)` for the final complex multiply.  The bound covers two
products per complex component, 24 accumulation updates, the four-lane NEON
reduction, and final oscillator multiplication.  It also reports the old
pairwise tolerance failures; it does not redefine that tolerance as passing.

Run on ARM:

```sh
./test_fir_forward_error_arm
```

A passing forward bound would substantiate cancellation and legal FP32
reduction-order error.  It would not establish estimator quality or speed;
the original component benchmark should run only after this diagnostic passes.
