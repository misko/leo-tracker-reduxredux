# Cost ceiling for one phase-coded stereo waveform scout

One shared scout across both primary lanes and every pairable residual would leave **47.42 CPU seconds** of measured cold acquisition work under an optimistic count-based transfer. The dense half-acquisition budget is **29.48 CPU seconds**. The warm scenario projects **41.16 seconds** of acquisition against **29.17 seconds** allowed even with the planned 24-second solver. This route stopped at the cost gate using existing measurements. [Frozen gate](shared-waveform-roof-protocol.md) · [Numeric receipt](measurements/shared-waveform-roof.json)

## What the scout could replace

The hypothesis scouts a single equal-power complex sum from both antennas, with a fixed unit-modulus frame phase sequence, and then verifies on each antenna's own signed I/Q. The earlier envelope experiment used a product of centered signal powers. It covered two of 80 dense factor phases and zero of 58 weak phases at its widest tolerance. The exact stereo FFT experiment instead batched the two original independent signals and found a slowdown. The partner-local experiments transferred one antenna's timing evidence to the other. Those results test different operations. The proposed linear combination remains untested. [Joint envelope](joint-envelope.md) · [Exact stereo FFT](stereo-fft.md) · [Partner evidence](../single-core-2x/receiver-lanes.md)

The installed detector independently confirms a primary on each antenna, subtracts its own pilot and verifies original signed I/Q on that antenna. The continuation histories remain separate by receiver, channel and RF. The prespecified primary-only case removes one native scout for every stereo pair. A more favorable case also removes one scout for each double-confirmed residual. It assumes each original residual waveform is still obtained by its own cancellation, and the mixed residual can find both antennas' signals. Singly confirmed residuals still use their original scout. Both projections grant complete seed recall, zero mixture overhead and a shared scout costing one average original scout. [Independent native paths](stereo-fft.md) · [Matched scout profiles](measurements/receiver-polyphase-timing.json)

| Matched panel | Original scouts per repeat | Scouts saved, primary alone / primary plus paired residual | Measured total scout share of native CPU | Optimistic native CPU reduction, primary alone / both |
|---|---:|---:|---:|---:|
| Weak, 18 stereo visits | 72 | 18 / 36 | 55.31% | 13.83% / 27.66% |
| Dense, 48 stereo visits | 148 | 48 / 68 | 67.28% | 21.82% / 30.91% |

Twenty double-confirmed dense visits can batch their two residuals. Another 12 have a single residual. Per-call averages pool primaries and residuals, so the sharing values are cost sensitivities. Even removing the entire timed scout stage on both antennas supplies an upper cost saving below the complete cold native cut required. The profile's timed stage includes preparation, timing and carrier search, refinement, and independent pilot confirmation, giving the hypothetical scout extra credit. [Equal-input profile and path receipt](measurements/shared-waveform-roof.json)

## Cold CPU and warm budget

Installed v3 used **37.34 CPU seconds** in stereo callbacks and **21.62 CPU seconds** elsewhere before solver handoff on the complete 6,765-visit dense recording. Holding the outside work fixed gives just **7.86 CPU seconds** for stereo callbacks at half acquisition CPU, a required **78.96% native reduction**. The originally observed outside-callback elapsed time was 61.96 seconds, already above the 49.76-second cold elapsed half. Cold wait can change with work and cache conditions. All CPU calculations below use the recorded outside work. [Complete dense attribution](acquisition-split.md)

| Hypothesis or boundary | Remaining callback CPU s | Cold acquisition CPU s | Warm acquisition sensitivity s | Solver time allowed at warm raw-to-exit half s |
|---|---:|---:|---:|---:|
| One shared primary scout | 29.19 | 50.81 | 44.55 | 8.62 |
| Share primary and double-confirmed residual scouts | 25.80 | 47.42 | 41.16 | 12.01 |
| Give all scout stages away | 12.22 | 33.84 | 27.58 | 25.59 |
| Original independent oracle, exact proposals supplied | 11.44 | 33.07 | 26.80 | 26.36 |
| Original separate cancellation, load and verification only | 10.65 | 32.27 | 26.01 | 27.16 |

The original-waveform directed oracle supplied exact scout timings and signed frequencies and knew which dense prefix lanes were empty. Its complete measured native calls averaged 1.692 ms per stereo visit. Cancellation, verifier load and verification alone averaged 1.574 ms per stereo visit. Transferring just those independent stages to the original dense visit count gives **10.65 CPU seconds**, exceeding the cold callback budget by **2.79 seconds** even with all scouts and preliminary pilot confirmation free. These are conditionally transferred native costs from the same dense prefix, and the two independent cost baselines have different measurement scopes. [Authentic directed timing](directed-verifier.md) · [Numeric comparison](measurements/shared-waveform-roof.json)

For the historical warm 113.02-second raw-to-exit timing, retaining the 3.34-second publication tail budgets acquisition at 24.68 seconds with a halved original solve, or 29.17 seconds with the planned 24-second solve. The warm column attributes the stored cold-run callback CPU one-for-one to the old warm acquisition, then holds the resulting 15.36-second remainder fixed. The most favorable shared-scout case would need a **12.01-second solver**, compared with 28.68 CPU seconds on the full-catalogue saved dense fit. Scope differences preclude an elapsed timing claim. [Historical clocks](first-55/stage-clocks.csv) · [Matched dense solver](full-family-amortized.md)

The calculation leaves room for a standalone native improvement and rules the shared-scout route out at the established 2× gate under the measured stage assumptions. The projection already gives the mixture and every proposal perfect recall for free. This experiment read no I/Q and established no weak or dense seed recall, antenna-swap behavior, mixture clipping or signed-output quality. Two arithmetic and accounting tests passed. [Calculation](shared_waveform_roof.py) · [Owned tests](../../../tests/pipeline_eval/test_shared_waveform_roof.py)
