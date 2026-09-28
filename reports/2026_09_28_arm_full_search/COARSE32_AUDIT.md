# ARM coarse-FP32 four-probe audit

This is a bounded portability and numerical-precision audit of the completed
ARM run. It evaluates the same four 2.5 MS/s probe-0 inputs used by the frozen
oracle: lower and upper edges, receiver 0 and receiver 1. The run retained all
11 coarse-CFO rows and all eight candidates per receiver. It is not a reduced
search result or an 80/90% recovery claim.

The copied receipts are in `results/coarse32-arm/`. The ARM build receipt binds
probe `1ca9d63db866116c5474fdfbedfb9b0a90b9f0f52494b2d09cf9507ee7ad0fde`;
the execution receipt is complete and records three repeats per probe.

## Parity result

The strict comparator marks all four records failed, as expected for this
variant. The only tolerance failures are the coarse outputs:

| Output | Failures | Maximum absolute difference | Comparator tolerance |
| --- | ---: | ---: | ---: |
| Full 11×3333 coarse grid | 4 / 4 grids | 2.8363340270898263e-7 | 2e-11 |
| Retained-candidate `coarse_score` | 31 / 32 | 1.4219198551934653e-7 | 2e-9 |

Every other compared numerical field remains inside its existing tolerance.
The largest non-coarse score difference is `verify_score` at
2.0261570199409107e-15. The largest acquisition/conditioned CFO difference is
5.820766091346741e-11 Hz, and the largest tracking-CFO difference is
2.837623469531536e-9 Hz. `fine_cfo_hz` is native-only diagnostic data and has
no frozen acquisition-result field to compare.

All 32 ordered candidates retain exact candidate count, retained-peak count,
coarse epoch, coarse bin, refined epoch, final epoch, frame support, and GLRT
completion identity. Exact bit equality is not expected for all floating
fields, but every final GLRT exact score, control score, and margin is within
the 2e-9 comparator tolerance. The two reference margin-gate positives are
both native positives and match one-to-one; there are zero misses and zero
added positives.

## Runtime receipt

The mean of the four reported `mean_cpu_ms` values is 3337.589109 ms
(range 3332.503580–3340.847672 ms). Across the four `timings_ms` records, the
mean stage values are:

| Stage | Mean CPU ms | Range CPU ms |
| --- | ---: | ---: |
| total | 3338.120913 | 3332.237130–3344.893830 |
| coarse | 1213.505190 | 1212.483240–1215.268860 |
| acquisition | 2070.725447 | 2064.048732–2079.304200 |
| GLRT | 37.370171 | 37.093620–37.648650 |

The result establishes that FP32 coarse accumulation changes the measured
coarse values enough to violate strict full-search parity, while this bounded
fixture preserved candidate identity and downstream FP64 final evidence.
