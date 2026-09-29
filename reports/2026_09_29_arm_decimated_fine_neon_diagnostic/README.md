# NEON FIR failure diagnostic

The original ARM component test failed its unchanged `3e-6 * max(1, |scalar|)`
bound before the benchmark ran.  This versioned diagnostic uses the same scalar
and NEON kernels and input patterns.  It prints the first failing pattern,
rate, output index, complex outputs, absolute error, original bound, local
24-sample input L1 norm, and modulated-filter L1 norm.  It exits nonzero on any
failure; it does not relax the qualification bound.

Code inspection finds no evident lane/index or conjugation reversal: `vld4_f32`
loads four interleaved complex samples, the constructed real and imaginary
vectors are reversed into newest-to-oldest order, and `vld2q_f32` supplies the
matching four complex taps.  The NEON kernel does change floating accumulation
order by keeping four tap residue classes in lanes and reducing them at the
end.  A failure with small output but large input L1 would support cancellation
as the cause; a large error relative to input L1, or a stable phase/sign error,
would instead indicate an algorithmic defect.

Run on the target with:

```sh
./diagnose_decimated_fir_arm
```

The diagnostic performs no benchmark and does not qualify integration.
