# Compact C post-coarse verifier

This experiment reduces the embedded receiver's post-coarse working set and measures the effect through the full dual-lane portable detector. Both builds run the same coarse detector and conditional retry policy from revision `234490f2b9b437d55ad4357c6ecc6dbad740bab6`. The detector replays stored CI16 through ranked fine CFO, conditioned CFO, held pilots and both integer and bracketed fractional GLRT gates. Position accuracy was unmeasured.

On 12 held stereo visits, the compact build reduced complete detector CPU by **8.2%**, wall time by **8.9%**, and observed peak RSS by **24.4%**, using the median paired reduction across eight native runs. The verifier workspace fell **59.4%**, from 5,858,144 to 2,378,232 bytes. All eight pairs completed faster. The compiler-reported main-to-fine C stack increased by 800 bytes.

| Native measurement | Stock median [range] | Compact median [range] |
| --- | ---: | ---: |
| Complete CPU per dual visit | 365.0 ms [351.0–383.3] | 335.7 ms [331.6–340.9] |
| Complete wall per dual visit | 371.6 ms [358.8–499.7] | 339.0 ms [332.3–352.4] |
| Verifier CPU per dual visit | 127.5 ms [112.6–141.2] | 97.1 ms [94.5–99.8] |
| Process peak RSS | 13.26 MiB [13.26–13.26] | 10.02 MiB [10.02–10.03] |
| Verifier workspace | 5.59 MiB | 2.27 MiB |
| Main-to-fine C stack | 40.39 KiB | 41.17 KiB |

The coarse grid accounted for 66–68% of samples in the separate gprof runs. Measured coarse CPU differed by a median of 0.2% between paired release runs. The verifier CPU fell 23.8% paired. The fine transform still accounted for roughly 0.4 sampled CPU seconds per held replay in each profiling build, so the speed result applies to the combined verifier changes. High shared host load widened wall-time variation. [Chart PDF](c-fine-memory.pdf) · [Measured values](stage.csv)

## Implementation

- The verifier retains its private lane copy as CI16 and converts integers to binary64 as each kernel reads them. The lane copy falls from 3,200,000 to 800,000 bytes.
- The first two fine FFT passes share 32 columns. The transform reads occupied pilot samples from the folded row and supplies zero padding on demand. The third and fourth passes share one column and compute only the requested frequency prefix. The prior rotation cache and FFT butterfly arithmetic carry through. The per-frame dense zeroing pass is removed.
- Exact and symbol-rolled held verifications share received energy and CFO phase. The rolled reference reuses fine FFT scratch after fine acquisition. The five integer GLRT evaluations share their carrier phase by CFO, and fractional GLRT constructs Lanczos indices and phase for one frame at a time. The correlation kernel retains its four-lane reduction order and both sides retain the same gate and tie policy.

The verifier accepts caller-supplied templates on the retained-seed path. The full detector uses its existing packed Qin representation to generate the lower- or upper-edge templates once per edge. This variant also supports the archived templates through the standalone verifier so comparisons cover the original producers' own values.

## Coverage and reproducibility

The timed held set contains four archived stereo captures from each of DS26-0237, DS29-0082 and DS29-0519. The archives have distinct producers and cover both edges. Each recording contributes one archived rejected, one dilute, one equivalent and one stereo-positive visit. Both arms receive identical samples, CFO bounds and both lane requests. The development set separately checks six previously frozen captures and their retained seeds, including DS26-0237 visit 1561 immediately above the fractional gate and visit 3235 below it. Synthetic controls exercise zero IQ, noise, operand ties, duplicated seeds, both Nyquist endpoints, shortened frame support, a 137-sample coarse-only input and one byte of missing CI16. A truncated input emits only the stream header before exit 2.

Both builds returned the same ordered coarse seeds, 28 verification groups and 224 ranked candidates per held run. The held set had 127 bracketed fractional results, 38 fractional passes and 26 candidates tagged as equivalent ties. The largest conditioned or held score difference was 1.39 × 10⁻¹⁶. Fine and acquired CFOs, integer and fractional GLRT values, fractional offsets, gate flags and candidate ranks matched exactly on the run. The frozen near-gate margins were 0.0250023136846505 and 0.0249283655881994. Their decisions matched. Synthetic controls included ten fine rank guards, ten conditioned ties and five GLRT bin ties, with all flags and ranks matching.

AArch64 QEMU matched 32 candidates through full raw detection and 16 through retained-seed verification, with score differences at most 1.12 × 10⁻¹⁶ and identical GLRT values and flags. Cortex-A9 QEMU produced byte-identical retained-seed packets for 16 candidates. Physical ARM timings are unmeasured. The component tests also compare the fine frequency-prefix output byte-for-byte at ten radix boundaries and exercise the negative, near-gate, edge and truncation controls.

The native GCC release builds use `-O3`, `-march=x86-64-v3`, `-ffp-contract=off` and `-fopenmp-simd`. Eight matched native pairs alternate CPU 10 and 11, with balanced arm order on each CPU. Each process starts fresh and reads inputs staged in tmpfs. The complete CPU and wall clocks cover the saved-IQ stream after entry to `main` through completed output, including setup and retries. Peak RSS comes from `/proc/self/status` `VmHWM`. The stack entry in the chart sums compiler-reported frames on the path from `main` to the fine FFT and omits system-library frames. The gprof runs are separate from the release timings.

The qualification receipt records individual clocks, matched inventory counts, flag counts, numeric differences, source SHA-256s, compiler commands and ARM checks. It records the stage and raw input seals as well. [Qualification receipt](qualification.json) · [Figure lock](stage-figure-lock.json)

From the repository, select a writable local scratch directory and run the same comparison. The inputs come from the archived reports and the C sources come from the pinned revision.

```bash
python3 -m tools.pipeline_eval.qualification.c_fine_memory_trial /dev/shm/leo-c-fine-memory
.venv/bin/python -m tools.pipeline_eval.qualification.c_fine_memory_stage /dev/shm/leo-c-fine-memory/qualification.json
```
