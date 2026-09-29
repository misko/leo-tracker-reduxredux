# Wave 7 complete FP32 final scorer experiment

This experiment replaces the final GLRT's arithmetic pipeline with FP32 while
retaining every one of the 16 frames, 64 symbols, FFT bins, candidates, and
the integer-offset final path. It consumes Wave6's already prepared normalized
FP32 dwell samples, builds rotated exact/control templates in FP32, uses NEON
symbol dots on ARM, persistent FFTWf 128/512 plans, and FP32 spectra, ceilings,
and selection. Public scores and estimates are widened to double at the output.
There is no FP64 fallback. This is an explicitly approximate scientific variant.

V1 used `cosf`/`sinf` for every rotated template sample. Its 704-dwell host
cohort recovered 19,217/19,581 frozen positive hits, with zero lost or gained
hit identities relative to Wave6, no margin-sign changes, and one tracking-CFO
change of one 512-bin step (443.892 Hz). Nevertheless, root's physical Cortex-A9
run rejected it: 893.340 ms total versus 863.029 ms for Wave6, and 119.40 ms
GLRT versus 88.78 ms, while retaining 119/119 hits.

V2 preserves V1 and uses the FP64 32-sample block-anchor construction of the
reference scorer, then narrows each rotated template once to FP32. This removes
per-sample trigonometry and makes the comparison fairer. `sources-v2` and
`builds-v2` are sealed independently from V1.

The final V2 host704 cohort recovered 19,217/19,581 hits, with zero lost or
gained hit identities. The final host32 cohort recovered 834/843. Every row in
both cohorts reports `final_scorer: fp32`. Host timing is diagnostic only:
host704 mean GLRT was 11.177 ms and fused total was 89.111 ms.

Root's matched physical Cortex-A9 ARM4 run retained 119/119 hits and all 182
emitted objects. Mean total time was 856.661454 ms versus 863.029 ms for Wave6
(0.74% lower); GLRT was 82.485837 ms versus 88.78 ms. This is a measured but
marginal improvement.

`test_float_final` compares the approximate path with the strict FP64 scorer at
all four rates on full-scale pseudorandom CI16, coherent, alternating
near-cancellation, zero, and partial-tail inputs. Its conservative absolute
score bound is `32768 * FLT_EPSILON = 0.00390625`, covering the longest symbol
dot, 16-frame reductions, and FFT stages. The observed worst error is
0.0017253260083694016 on a cancellation case; ordinary cohort differences are
about 2e-6. Residual CFO is allowed at most two 512-bin steps in the component
test. Host and sanitizer units pass, and ARM cross-builds with warnings as
errors.

Rebuild with:

```sh
python3 reports/2026_09_29_arm_wave7_float_final/build_v2.py
```

Final V2 ARM runner SHA-256 is
`de1d5a81079bf298553e0cb300f4fc055c61064f2aa4a383be4227b73d7184ae`;
the ARM float-final unit is
`350434829656c3e874b43ee600bfa0b607a5151dbadd15db25c67c03c58b2172`.
The manifest SHA-256 is
`a32d38f769843269097d31ee3c7ca5affa7b28786e1dfce99ae6f657220a8a22`.
