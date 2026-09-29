# QUARANTINED — FP32/NEON fine-FFT input preparation

**Do not promote or use this variant.** The prepared-input loop has a confirmed
terminal-frame heap overread. Its availability predicate validates only the
last active template symbol, while the FP32 scalar/NEON loop loads the full
`w->n` prepared buffer, including its zero-template tail. This correctness
failure overrides the earlier inherited host, sanitizer, and physical ARM unit
passes. The sealed build and timing artifacts remain evidence of the rejected
implementation; their candidate benchmark is not qualified.

The dedicated reproducer is
`tests/test_fine_precision_tail_asan.c`
(`07963906221d19402b7a0a17318cd5863df7c98575b04e6a7e6f67576eb040bd`), run
by `tests/run_tail_asan.sh`
(`0fd06feb924aad9d645eaa2ed86590e6a3fe107adbf61d4f022a58037f420a8d`) against
the sealed `sources/fine_precision.h`
(`f0b903821128cc11f7d678824b31e8efc94aae867c3900ebe3edd202d08847aa`). It
reproduces an AddressSanitizer heap-buffer-overflow at `fine_precision.h:194`;
the captured stderr hash is
`dd8fc9f0a85c05f6faa8f8adb4a496323b6fd8d3c7f955d705a824b364c56569` in
`tests/tail_asan.stderr`. The test chooses the nearest frame accepted by the
old predicate but not large enough for the full prepared-buffer read, for all
four supported rates. No repair is made to this sealed rejected source.

This bounded Wave3 experiment preserves the 500 Hz fine grid, FFT lengths
5000/10000/15000/20000, two selected frames, frequency bounds, interpolation,
conditioned behavior, and final FP64 GLRT. It changes only preparation of the
already-FP32 fine FFT input and its normalization energy.

The Wave3 coarse stage already converts the complete input window to FP32 as
`sample / 32768` and builds an FP64 energy prefix. The baseline fine stage
ignored both: for every candidate frame it reread complex FP64 samples,
recomputed sample energy point by point, performed a complex FP64 template
product, and narrowed that result to FP32. This candidate caches
`32768 * conj(exact)` as an FP32 template, multiplies four complex lanes with
Cortex-A9 NEON, and obtains energy from FP64 prefix differences over the same
active symbol ranges. Opposing scale factors retain the baseline FFT units.
The host build uses the same scalar FP32 arithmetic. Final scoring continues to
read the original FP64 samples and templates.

`build.py` produces host, sanitizer, and ARM cross-build receipts. Host and
sanitizer component tests cover all four rates, full and partial input, extreme
CI16-valued samples, frame budgets 1/2/4/8, and require every tested fine score
to remain within `2e-5 * max(1, abs(reference))` of the original FP64 fine
estimator. The fused inherited ARM unit suite was also executed physically;
its fine-budget test covered the NEON path at all four rates and budgets
1/2/4/8.

## Historical preliminary standalone qualification (confounded and unqualified)

The first qualification accidentally used the standalone regional runner and
frozen external feature regions. Its 32-dwell result was 835/843; its 704-dwell
result was 19233/19581 with 18610 unmatched hits. Those figures cannot be
compared with Wave3's internally generated proposals or fused timing and are
retained only as component evidence.

## Historical fused Wave3 qualification (unqualified)

`builds-fused` contains a fresh immutable host/sanitizer/ARM matrix for the
actual Wave3 fused resampled/omit-power/rank/boundary runner. The fused evaluator
uses `arm_wave3_combined/host704` as its direct reference and the frozen
`arm_proposal_features/host704-omit-power-v1/rows.jsonl` feature rows. Its
host standard audit exactly matches the control aggregate: 19226/19581 recovered
hits and 21505 unmatched positive hits.

Host timing did not demonstrate a speedup. Mean fine-stage time was 12.281 ms
per dwell, versus 11.348 ms for the directly comparable Wave3 control. Mean
fused total was 102.217 ms versus 92.870 ms. Physical Cortex-A9 timing was
also slower: candidate total was 1713.365 ms and fine stage 316.944 ms, versus
the base 1710 ms and 309.8 ms. This variant is not selected. An aggregate ARM
quality audit remains pending, so this report makes no direct ARM quality claim.
Neither timing result is a qualification because the terminal-frame overread
invalidates this implementation.

Evidence:

- `builds/{host,sanitizer,arm}/build-receipt.json`
- `builds-fused/{host,sanitizer,arm}/build-receipt.json`
- `arm-fused-units.json`
- `tests/test_fine_precision_tail_asan.c`
- `tests/run_tail_asan.sh`
- `tests/tail_asan.stderr`
- `../2026_09_29_arm_subsecond/host32-fine-input-neon/`
- `../2026_09_29_arm_subsecond/host704-fine-input-neon/`
- `host704-fused/`
- `../2026_09_29_arm_wave3_combined/host704/`
