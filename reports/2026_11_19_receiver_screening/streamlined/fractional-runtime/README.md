# Ordered fractional interpolation in ordinary wave8 GLRT

The new kernel reduced median warm authenticated saved-IQ-to-candidate wall time from **25.44 to 22.88 ms** on x86. It met the 20 ms deadline in 12 of 60 calls, up from 5 of 60. The median missed the predeclared 20 ms gate. All 12 admitted real dual-receiver visits and eight synthetic controls produced identical canonical detector payloads within each architecture. Four original capture exclusions stayed in the roster. Each timing comparison uses the reusable CI16 preparation parent in both builds. [Protocol](PROTOCOL.md) · [Qualification data](qualification.json)

| Boundary | Prepared parent | Ordered interpolation |
| --- | ---: | ---: |
| Warm x86 median, mmap + SHA-256 through candidate response | 25.44 ms | 22.88 ms |
| Warm x86 p90, same boundary | 30.64 ms | 27.82 ms |
| x86 detector CPU over 60 calls | 1,357.92 ms | 1,251.56 ms |
| x86 fractional-epoch CPU over 60 calls | 566.63 ms | 484.29 ms |
| Cortex-A9 QEMU median process wall, one CLI process per visit | 1,275.48 ms | 1,242.02 ms |
| Emulated detector CPU over 12 calls | 4,507.86 ms | 4,474.43 ms |
| Emulated fractional-epoch CPU over 12 calls | 2,042.06 ms | 1,987.58 ms |

On x86, the full fractional-epoch stage used 14.5% less CPU and the full detector used 7.8% less CPU. The warm host boundary excludes decompression of the original archive, RF input and the position solver. The Cortex-A9 numbers are QEMU measurements and include a freshly launched CLI at each visit in the process wall column. Peak QEMU subprocess RSS was 47,160 KiB for the parent and 48,144 KiB for the candidate. The paired host harness peaked at 222,372–223,604 KiB with both libraries, contexts and the Python runner resident.

The wave8 compiler generated separate scalar interpolation chains for the two components. The new x86 kernel packs the real and imaginary parts into two binary64 lanes and accumulates all 16 taps in their original order, including ordinary normalization division. The coordinate and Lanczos weights are reused for a symbol whose sample coordinates, including the permitted offset, occupy one binary64 binade. Boundary symbols preserve the old per-sample coordinate calculation. The binade rule also preserves rounding at ties because each integer spans an even count of representable values over this range. The scalar ARM candidate uses the same binade rule and tap order. The component checks exercise both paths across powers of two and offsets near rounding ties. No fractional grid points, templates, gates, or support samples were removed.

Empty and Gaussian noise controls produced zero positive factors. Both physical receivers in both bands detected the original weak carrier. The additional planted pair, at epochs 731 and 746 with a separation of 227.2727 kHz, recovered both known epochs and carriers in each physical receiver and preserved every detector field, including alternate alias candidates. [DS26 host](DS26-0036-host.json.gz) · [DS29 host](DS29-0082-host.json.gz) · [DS26 QEMU](DS26-0036-arm.json.gz) · [DS29 QEMU](DS29-0082-arm.json.gz)

## Fresh position comparison

The fresh position fits used eight DS26 and four DS29 measured candidate visits with all other authenticated ordinary factors. The composite scientific factor bytes, causal catalogue and Graph observation digest matched the prepared parent. Published and forced positions, withholding and the RF result matched exactly in both calibration arms. Geographic accuracy and frequency residual are reported separately. [Position receipts](position-receipts.json)

| Recording | Replayed + archived visits | `c = 0` error | Fitted `c` error | `c = 0` / fitted Doppler RMS |
| --- | ---: | ---: | ---: | ---: |
| DS26-0036 | 8 + 6,757 | 0.654 km | 0.739 km | 232.44 / 209.30 Hz |
| DS29-0082 | 4 + 4,864 | Withheld | Withheld | 260.24 / 214.02 Hz, forced diagnostics |

DS29 withheld for weak held-track support. The partial detector substitution scope is distinct from the single-visit detector timing. [Evidence seal](prediction-lock.json)

## Reproduction

The qualification module `tools.pipeline_eval.qualification.fractional_runtime_eval` accepts `build` or either recording ID, `--arch host` or `--arch arm`, a local `--work` directory and the reusable preparation study’s `--parent-work`. Use a single pinned CPU and one numerical thread. The position module `tools.pipeline_eval.qualification.fractional_runtime_position` takes the same `--work` with each `--case`, then no `--case` to package the results. The standard `figures --panel screening` IDs are `fractional_runtime` and `fractional_runtime_position`. [Source hashes and build receipts](source-lock.json)
