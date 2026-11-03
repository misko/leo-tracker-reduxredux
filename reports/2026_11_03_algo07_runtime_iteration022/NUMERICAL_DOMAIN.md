# Numerical-domain review: integer screening with exact retained scores

This review applies to the pinned Linux/x86-64 integer screen and batched FP64
oracle in iteration 021's detector build. It does not qualify the earlier FP32
screen or an arbitrary approximate kernel. The screen produces proposals; only
original FP64 scores and refinement neighbors reach retained scientific output.
Release qualification additionally requires complete native parity, three
paired detector benchmarks, both calibration arms, frozen policy checks and an
installed canary. This document alone is not deployment evidence.

## Admitted domain and arithmetic

The runtime checks complex128 finite arrays, at most 1,000,000 IQ samples,
nearest rounding, valid symbol geometry, at most 4,096 taps and at most 10,000
frame/symbol supports. Frequencies, sample rate, amplitudes and normalization
must satisfy the existing bound checks. The integer variant additionally
requires exactly integral IQ components in [-32767, 32767]. All-zero inputs,
degenerate reference energy and unsupported geometry use the original full
grid. The acquisition adapter uses the screen only when its absolute score
bound is at most 0.01. Larger bounds also use the original full grid.

The pinned native code uses ordinary FP64 operations, sin/cos, square root and
division without fast-math compilation. AVX-VNNI support is explicitly checked;
absent support keeps the original path. This review assumes the ordinary
IEEE-754 nearest-rounding arithmetic and finite sin/cos range supplied by this
pinned Linux runtime. Unsupported rounding is rejected before screening.

## Integer samples and energies are exact

Let `X <= 32767` bound each integer IQ component and `N <= 1,000,000`. Each
power sample is an integer below `2 X² < 2^31`. The complete prefix is below
`2 N X² < 2^51`, well within FP64's exact-integer range. The deployed
`_power_prefix` forms `real*real + imag*imag` and a cumulative sum. Every product,
sum, prefix and difference of prefix entries is therefore exactly representable.
This argument uses the actual power implementation, not an absolute-value/sqrt
identity that might introduce rounding. The boundary check confirms all
1,000,001 prefix values at maximum IQ amplitude against integer arithmetic.

The inherited energy-ratio allowance is at least one and remains conservative;
the integer variant does not need a cancellation correction for these exact
prefixes. Keeping that allowance enlarges the screening interval.

## Reference quantization and int32 accumulation

For maximum tap count `n` and maximum IQ component `X`, the code uses

`Q = min(32767, floor((2^31 - 1)/(2 n X))) - 1`.

For maximum selected reference component `R`, quantization scale is
`s = Q/(2R)`. The rotation's real and imaginary components are bounded by `2R`.
The one-count margin and the finite, bounded FP64 scale calculation keep rounded
reference components within signed int16. Integer sample conversion is exact.
Each real or imaginary dot product has absolute L1 bound `2 n X Q < 2^31`.
Every partial sum is bounded by the same L1 sum, so the signed int32 dot-product
accumulation cannot overflow. Negative-reference packing also stays in range.

The boundary experiment checks the largest tap count, largest IQ magnitude,
coherent sums and reference quantization ties. It covers both cases admitted to
screening and cases routed to full search by the broad-bound cost gate.

## Score-error bound

For a selected reference segment `r` of length `m`, component quantization
contributes at most approximately `0.5/s` per real or imaginary component. Thus
the complex reference-error norm is bounded by `sqrt(2m)/(2s)`, apart from tiny
FP64 rotation/scaling terms. Cauchy–Schwarz bounds its contribution to normalized
correlation by that error norm divided by `||r||`. IQ normalization is exact as
shown above. Magnitude is 1-Lipschitz, so this also bounds the normalized
magnitude difference. Averaging frame/symbol supports cannot increase the bound.

The implementation uses twice this leading term:

`B = max_segments sqrt(2m)/(s ||r||) * sqrt(energy_ratio) + 1e-10*(1+relative)`.

The factor-two margin covers the FP64 reference-energy estimate, rotation,
rescaling, magnitude and averaging arithmetic. Its size is substantial even at
the least favorable quantization margin: since `||r|| <= sqrt(2m) R`, half the
leading term is at least `1/Q >= 1/32766`, about 3.05e-5. By comparison, the
admitted operation counts give FP64 relative rounding factors below 1e-12 for
reference/correlation work and about 1.2e-12 for support accumulation. Applying
Cauchy–Schwarz before cancellation bounds normalized absolute roundoff; a loose
1e-8 allowance remains far smaller than the unused quantization margin. The
explicit 1e-10 term and outward rounding enlarge the interval further.

The amplitude and reference-energy bounds avoid FP64 overflow in correlation
or normalization and keep positive normalization away from underflow. Individual
tiny reference components may underflow; their total normalized contribution is
negligible relative to the above margin. No error bound is inferred from the
observed agreement or from the final satellite/position answer.

## Why selected peaks remain the same

The selector expands interval endpoints outward. Any true local peak must have
an upper bound at least as large as both neighboring lower bounds. Initial
proposals and their neighbors are evaluated exactly. The selector then requests
every still-possible peak whose upper bound can reach the current kth verified
score, including ties. This repeats because newly discovered peaks can change
the suppression chain and lower the threshold.

At termination, every unexamined possible peak ranks below the kth retained
score. It cannot affect the original descending greedy selection. Verified
local peaks use exact neighbors, and tie order matches the original score,
absolute-CFO, epoch and discovery-order key. Circular separation and noncircular
local-peak/refinement boundaries match the original implementation. Insufficient
verified peaks or an observed interval violation use complete FP64 evaluation.
An observed-violation check cannot validate unexamined scores; that is why the
separate numerical bound is necessary.

## Batched exact oracle

The sparse extension changes epoch indexing only. It retains the same reference
rotation, sample and prefix arrays, CFO execution tiles, correlation arithmetic,
symbol/frame accumulation order, magnitude and normalization. Invalid tail
supports are skipped independently for each requested epoch. Duplicate and
out-of-order requests are supported. The complete original extension remains
available for fallback, and unsupported sparse hardware uses the original
single-column oracle. Actual native stress tests compare bit patterns, not a
relaxed tolerance.

## Evidence and scope

The [domain challenge](receipts/domain-review.json) covers 135 combinations of
tap counts 1–4096, IQ magnitudes 1–32767, reference scales 2^-250–2^39, coherent
signals, quantization ties and cancellation. The largest observed error uses
about half its computed bound, consistent with the factor-two margin. Six
unsupported-input/rounding checks reject their inputs as intended.

This combines an arithmetic review with regression evidence on the specified
domain; finite tests alone do not establish correctness for all inputs or other
platforms. The helper's `production_qualified=False` field remains a statement
that a standalone bound evaluation is not a deployment attestation. Qualification
of the complete pinned release is recorded in the release manifest and its
evidence, not inferred from that helper field.
