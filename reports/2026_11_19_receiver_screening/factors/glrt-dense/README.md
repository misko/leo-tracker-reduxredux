# Full-epoch Q10 sliding-tone GLRT bank

The Q10 bank saved **19.04% coarse CPU** and **14.33% full detector CPU** on 15 processed held 20 ms visits. It passed the full-detector target and fell short of the predeclared 20% coarse target. All 16 scheduled capture results were byte-identical to the installed producer, including the one original capture exclusion. The 23 integer and 23 fractional positives had the same receiver, rank, offsets, CFO and margins. The six synthetic controls on each capture configuration also matched byte for byte.

| Held session | Scheduled / processed | Coarse CPU saved | Full detector CPU saved | Fractional positives retained |
| --- | ---: | ---: | ---: | ---: |
| DS26-0036 | 8 / 8 | 19.86% | 15.85% | 6 / 6 |
| DS29-0082 | 8 / 7 | 17.96% | 12.69% | 17 / 17 |
| Pooled | 16 / 15 | 19.04% | 14.33% | 23 / 23 |

The signed IQ, all raw epoch phases, original anchor symbols and 21 trial CFOs enter both runs. Each held visit used three alternating timing pairs. Pooled coarse CPU was 12.976 s for binary64 and 10.506 s for Q10. Full CPU was 24.817 s and 21.260 s respectively. Median full CPU was 536 ms and 485 ms per 20 ms visit. The speed result concerns the already accelerated binary64-coarse, conditioned-CFO and fused-GLRT stack. This CPU cost still exceeds a continuous 20 ms compute budget.

The bank multiplies each CI16 aperture sample by its pilot-tone phase in binary32 and rounds the real and imaginary products to integers at scale 1024. The kernel scans eight samples at once with unsigned 32-bit prefixes. Prefix differences preserve the quantized aperture sums even when the prefixes wrap, because each 44-term real or imaginary sum is below the signed 32-bit magnitude limit. The raw bound is approximately `44 × sqrt(2) × 32768 × 1024 = 2.088 × 10^9`. Binary32 and integer rounding add far less than the remaining approximately 59 million counts. The kernel converts the exact modular differences to binary32, restores phase and uses the existing pilot-symbol folding arithmetic.

For a nonzero aperture with IQ norm `E` and length `L`, the added per-tone complex error is bounded by `γ20 × sqrt(L) × E + (1 + γ20) × sqrt(2) × L/1024`. Here `γ20` is the standard binary32 rounding factor for 20 operations. The kernel adds this term across eight tones, normalizes conservatively with the largest reciprocal IQ and template norms, and adds the original spectral-grid error allowance. Every plausible contender and its neighbors goes through the original direct scorer. The original local-maximum test, tie order and nonmaximum suppression apply at exact scores. Ambiguous cutoffs use a complete direct fallback. None of the 117 held grid calls in either arm needed that fallback. The maximum Q10 score bound was `4.709e-5`. The median repaired cells per held Q10 call was 160 of 279,993.

Each grid still generates 33.59 million overlapping tone outputs. The Q10 kernel uses an eight-lane integer scan in place of the four-lane binary64 modulation and serial binary64 prefix. Its two integer prefix buffers occupy 1,376 bytes, half the binary64 stack space. It adds 19,136 bytes of temporary binary32 coefficient arrays per CFO, reusing the existing dense arrays of at most 5,844,432 bytes. The implementation adds 155 lines of C and a 76-line adapter. It preserves the original exact direct repair and duplicates the tone-to-anchor folding routine so the measured binary64 source remains immutable.

The held synthetic cases include the amplitude-128 pilot at epoch 735, three samples from the earlier stride-six lattice. The DS26 stride-six experiment missed this plant on both receivers. Q10 recovered it on both with the original fractional output and margins of 0.671 and 0.686. Both capture configurations also preserved the on-lattice faint pilot, strong plant, and adjacent-CFO pair. Empty and noise controls produced zero positives in each mode.

## Partial-IQ position confirmation

Both paired v5 runs are fresh. One uses the actual Q10 outputs from all eight held DS26-0036 visits, 16 receiver rows, plus the 6,757 other valid archived visits. The other uses the original archive. The native document and request hashes distinguish the runs. Prepared observations, tracks and final owners agree exactly, as do coordinates and frequency scores within each calibration arm. Only DS26-0036 received this downstream confirmation.

| Calibration arm | Position error | Conditional RF RMS | Frequency score |
| --- | ---: | ---: | ---: |
| `c = 0` | 1.278365 km | 74.760916 Hz | 25,232.145635 |
| Fitted `c` | 1.208143 km | 74.682298 Hz | 25,232.285586 |

[Q10 position](positions.jsonl.gz) · [Capture-era archive control](control-positions.jsonl.gz) · [Prediction seal](prediction-lock.json)

The [protocol](PROTOCOL.md) and [source lock](source-lock.json) fix the roster, compiler source inputs, seeds, scoring identity and acceptance criteria. The six compressed block receipts retain the native candidates, full public payloads and per-repeat timings. [Qualification](qualification.json) reports the pooled gate and one-to-one positive audit.

Reproduce each detector block with `python -m tools.pipeline_eval.qualification.dense_q10_eval --case CASE --split SPLIT --out RECEIPT`. Place the named original producer directory first on `PYTHONPATH`, pin the selected CPU and set numerical thread pools to one. Use `--controls` for the development block. Run `python -m tools.pipeline_eval.qualification.dense_q10_position prepare --work WORK` to bind the raw output factors to a distinct composite. Use the same module to fit `dense_q10` on CPU 2 and `dense_q10_capture_control` on CPU 3, then run `package` to verify and seal the pair.
