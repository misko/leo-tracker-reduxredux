# Wave 8 frontier plus complete FP32 final scorer

The conditioned stage has no high-confidence unchanged-work reuse left. Its
phase table is already cached by `(n, rate)`, and complete boundary results are
cached by `(epoch, sample_count, center CFO)`. The expensive frame moments use
`samples[epoch + frame + k] * conj(template[k]) * exp(-i*center*k)`, so changing
either epoch or center changes every weighted sequence and moment. Reusing
moments across those keys would require another approximation, while identical
keys already hit `final_conditioned_cache`.

This fallback experiment therefore preserves the frontier method exactly:
eight proposal frames, half proposal FFT grid, tracking minimum one, radius-one
regions, full coarse support, and fine frame budget two. It adds the previously
qualified complete FP32 final scorer V2 with block-anchored rotations, NEON
dots, persistent FFTWf 128/512 plans, and FP32 spectra/selection. It remains an
explicit approximation without FP64 fallback.

Host and sanitizer units pass, including the strengthened float-final oracle;
the ARM artifact cross-builds with warnings as errors. The receipt-bound
host704 cohort emits 77,894 candidates and recovers 18,465/19,581 frozen
positive hits, identical to the full-coarse radius-one frontier control. The
identity audit reports 18,465 matched hits on each side with zero lost and zero
gained identities. Host timing is slightly slower (60.171 ms fused versus
58.432 ms control, GLRT 9.636 versus 8.180 ms) and is diagnostic only; the
standalone float-final V2 improvement was Cortex-A9-specific and marginal.

Final ARM runner SHA-256 is
`6ab2f8750a79fa1d4248a442e6a9d22b1049a69d3bbfe9b84cc59a47f407283f`;
ARM float-final unit SHA-256 is
`5b7076cd70732e85f80f3f1c30d3730ac80d154bea9bc105be3e7ecda15dce5b`;
ARM receipt SHA-256 is
`a635254d5df85ae601f3a7d9bcc4ff8ccf788458e25619aa0d83da4dcc17cfce`.
No physical ARM execution was performed here.

`prepare_sources.py` records the deterministic transplant from the sealed
float-final V2 source. Rebuild with:

```sh
python3 reports/2026_09_29_arm_wave8_frontier_float_final/build.py
```
