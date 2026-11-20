# Roll the Qin pilot tone correlators on retries

Keep the prepared FFT for the 12-anchor primary. The 22-anchor rolling bank saved **32.44 ms per grid** in development and **35.32 ms (8.15%) of complete detector CPU per dual visit** on the two blind visits that actually retried. Across six blind visits on three installed producers, all 60 timed calls preserved the complete ordered detector payload and archived factors. The retry-only candidate cleared the gate for a bounded whole-waveform replay. [Stage chart](stage.pdf) · [Matched CPU and wall timings](stage.csv) · [Protocol](PROTOCOL.md) · [Qualification seal](qualification-lock.json)

| Anchor count | Prepared CPU median | FP64 recurrence | FP32 recurrence | FP32 with phase pairs |
|---|---:|---:|---:|---:|
| 12 | 53.45 ms | 60.45 ms | 50.51 ms | 54.91 ms |
| 22 | 99.06 ms | 82.74 ms | 73.00 ms | 66.82 ms |

The best primary paired median saved 2.92 ms, short of the 10 ms replacement gate. At 22 anchors, the binary32 phase-pair result exceeded the retry-only gate of 15 ms. Development measured both physical lanes and both anchor counts on each producer, with five rotating runs per mode. The complete detector used the qualified four-frame fine CFO transform, row-wise coarse selection, and the same conditioned and GLRT refinement paths. [Development grid comparisons](summary.json) · [Four-frame fine CFO qualification](../../retry-and-transfer/fine-batch/README.md)

## The eight-tone recurrence

The installed reference bank uses eight centered Qin tones at ±117,187.5, ±351,562.5, ±585,937.5, and ±820,312.5 Hz. Both edges have those relative frequencies and their own transmitted QPSK states. For coarse CFO f and pilot tone ν, the factor a = exp(−2πi(f + ν)/Fs) gives the geometric progression over the 44 taps. The correlation C[p] is the sum of x[p + t] a raised to t from t = 0 through t = 43. Moving the aperture one sample gives **C[p + 1] = a⁻¹(C[p] − x[p]) + a⁴³x[p + 44]**.

The kernel evaluates the eight responses once per sample position and coarse CFO, applies the pilot phases, and reconstructs each anchor's complex correlation before taking its magnitude. The phase-pair variant shares the four possible relative QPSK rotations of each adjacent tone pair across anchors. A coincidence of tone plus CFO frequencies would require tone and 80 kHz lane offsets with the reduced ratio 128 to 375, outside the eight-tone and 21-lane ranges. [Kernel](../../../../tools/pipeline_eval/variants/sliding_pilot.c) · [Template model and physical support](../../../../tools/pipeline_eval/variants/sliding_pilot.py)

Capture-era floating-point symbol classification places tap zero in the preceding symbol for one primary anchor and four retry anchors. The implementation restores those taps explicitly. After seam repair, the physical QPSK model's largest tap residual was 9.02 × 10⁻⁸ and its largest relative row residual was 2.90 × 10⁻⁸. Even with each tone coefficient refitted, the largest relative residual was 2.80 × 10⁻⁸. The stored complex64 templates retain rounding outside the eight physical tone directions. [Template fit and seam inventory](summary.json)

The binary32 path reseeds every 128 starts. A separate unrebased binary64 run across 199,957 starts, audited at 257 positions for each tone of the first CFO row on each development lane, had a maximum normalized drift of 1.63 × 10⁻¹³. The rolling grid uses the original sample-energy prefix and template energy. It includes each valid frame and anchor window through the trailing support boundary and divides by 168–180 primary or 308–330 retry contributions. The maximum dense errors relative to the prepared float32 grid were 2.38 × 10⁻⁸ for FP64, 9.10 × 10⁻⁸ for FP32, and 9.14 × 10⁻⁸ for paired FP32. All 36 development comparisons preserved the retained-key order. The rolling scores are approximate. [Numerical and support receipts](summary.json)

## Blind transfer and work removed

The blinded roster used visit validity and a fixed hash order. The six dual visits covered 96 public candidates, including 79 integer gate rejections, and 54 archived factor candidates, including 37 fractional gate rejections. The lower DS26-0237 visit 64 and upper DS29-0082 visit 102 exercised genuine retries. Their ten paired full-detector CPU gains ranged from 1.45 to 64.41 ms. Median paired wall savings were 33.67 ms, with differences from −86.80 to +87.10 ms. Across all 30 blind pairs the median CPU saving was 4.86 ms. Four visits used only the prepared primary in both arms. [Blind visit and gate summaries](summary.json) · [Frozen valid visit roster](input-lock.json)

Each measured retry removed 191,037 inverse FFTs while retaining the two primary grids. The replacement evaluated 33,592,776 tone updates, 262,584 reseeds and 89,348,952 folded anchor magnitudes. The main rolling input, norm and scratch arrays occupy 2.66 MB, with a separate 2.24 MB output grid. The prepared retry named FFT buffers occupied 2.07 MB. The AVX2 library is 32,080 bytes. [Per-grid work counters](DS29-0082.json.gz) · [Component tests](../../../../tests/pipeline_eval/test_sliding_pilot.py)
