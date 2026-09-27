# Fractional coefficient-transpose GLRT result

## Decision

Reject this candidate for acceleration. It stayed well inside every frozen
numerical tolerance, but it was slower than the unchanged full-aperture GLRT
when coefficient construction was charged on every invocation. The
preregistered rule therefore stops the experiment after the first variant.
There was no second approximation variant, holdout evaluation, production
change, or ARM performance claim.

## Scope and method

The candidate changes only the fractional, final full-aperture known-state
GLRT. It algebraically transposes the 16-tap Lanczos interpolation and
64-symbol pilot correlation. It retains separate exact/control coefficients,
early/late symbol-diversity regions, support bounds, ceiling and FFT scoring,
peak selection, and residual-CFO calculation. Integer epochs use the unchanged
reference path. Coarse timing, partial-frame confirmation, blind acquisition,
and ranking are outside this experiment.

Floating-point sample positions can acquire different fractional parts and
base shifts at binade boundaries. The implementation therefore observes the
actual pattern used by the reference interpolation and builds a distinct table
when the pattern or early/late region differs. Within a table build it reuses
Lanczos weights only when the actual fraction is exactly equal. Tables are
scoped to one call and rebuilt for every timed call. This prevents a repeated
benchmark coordinate from receiving an unrealistically free persistent cache.

The evidence contains 31 receiver-cases:

- 24 constructed controls at 2.5 and 5 Msps: eight injected pilots, eight
  noise controls, and eight tone controls;
- seven existing 2.5 Msps same-visit development oracle coordinates.

The latter coordinates are useful only as a kernel microbenchmark because they
were obtained from the same visit and are not causal predictions. Constructed
controls check behavior but do not calibrate a classifier false-positive rate.
No holdout IQ was opened.

Timing used five warmups followed by 50 repetitions for each receiver-case.
The receipt records medians of internal process CPU and monotonic wall time.
Candidate `total_cpu_ms` includes coefficient construction and coefficient
dots. The additional reference correlations used solely for numerical
diagnostics run after the candidate timer and are excluded from that total.

## Numerical result

| Check | Observed | Frozen bound | Result |
|---|---:|---:|---|
| Maximum pre-FFT correlation relative error | 8.495e-16 | 5e-12 | pass |
| Maximum ceiling relative error | 3.643e-16 | 5e-12 | pass |
| Maximum exact-score absolute error | 3.331e-16 | 5e-12 | pass |
| Maximum control-score absolute error | 4.163e-17 | 5e-12 | pass |
| Peak-bin changes | 0 | 0 | pass |
| Residual-CFO changes | 0 | 0 | pass |
| Margin-gate changes | 0 | 0 | pass |
| Trusted-gate changes | 0 | 0 | pass |

The baseline and candidate both passed the frozen margin gate on all eight
injected-pilot controls and on none of the eight noise or eight tone controls.
They both passed all seven same-visit development-oracle cases. These are
within-coordinate equivalence checks, not a claim that the controls or oracle
measure prospective detection performance.

## Timing result

| Cohort | Cases | Baseline median CPU | Candidate median CPU | Candidate / baseline | Build median | Dot median |
|---|---:|---:|---:|---:|---:|---:|
| All | 31 | 0.16385 ms | 0.17160 ms | 1.0473 | 0.07879 ms | 0.03184 ms |
| 2.5 Msps | 19 | 0.15475 ms | 0.16275 ms | 1.0517 | 0.07460 ms | 0.03018 ms |
| 5 Msps | 12 | 0.28965 ms | 0.32773 ms | 1.1315 | 0.20345 ms | 0.04392 ms |
| Same-visit oracle | 7 | 0.15720 ms | 0.16628 ms | 1.0577 | — | — |

A ratio above one means the candidate costs more CPU. Coefficient construction
alone consumed nearly half the all-case candidate median, erasing any benefit
from the transposed dot product. This kernel result cannot provide a 10x
pipeline speedup and does not merit integration into cached tracking.

A future persistent or fraction-merged cache would be a different numerical
and causal design. It would need a key containing the exact CFO, offset,
early/late region, and observed floating-point position pattern, or a
pre-established conservative error bound for merging patterns. That design was
deliberately excluded here and was not tuned after seeing these results.

## Provenance

- Dataset manifest SHA-256:
  `ce3a22f10abefca4623affe006331b770dad5d3788d99aa44bdad93d2f75af48`
- Existing oracle receipt SHA-256:
  `883590da488317f9c1d68414b687c77adfd2f6d3090f7fd719fd23ef5e17512a`
- Frozen design SHA-256:
  `7733f21f2f2e50c1a45ff4561c1e4e3f175602dfa768f241f015f032a9692a39`
- `coeff_glrt.c` SHA-256:
  `59c8735744701b83424f56b070cc78946e92713d4e502dfe2a595f32bc681b01`
- `coeff_glrt.h` SHA-256:
  `de85833d4f7bd37b654b6c1ec5272033e5c887d8e314f64359e7be9c38c2f43d`
- `coeff_glrt.py` SHA-256:
  `8f081ccf927687655ce64befcfeaa9a61281aa2d7912d68c2d2161f4e43ad2ff`
- Experiment runner SHA-256:
  `8671741724e8b05d78448ec11befb7180e273cd34117ba778fa42e083716ad92`
- Shared library SHA-256:
  `b1c9c77df211189427fa3750d4dcce4ba4be9c2a2aa72234050b9db9cb5f3859`
- Build receipt SHA-256:
  `0ae1c6d2bda4afb254d5ca3b57b5e3a5506b2b2639244c8d7852438a3133cf7b`
- Row-level result SHA-256:
  `9afee4dfd7583f0c4fc7cea57af57cb476db956a7edcfc622e6a8451cb97ad3c`

The server measurements do not establish ARM cost. The candidate remains a
research artifact and makes no change to RF, deployment, or production code.
