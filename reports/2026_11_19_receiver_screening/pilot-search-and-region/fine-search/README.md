# Prune the original fine CFO transform

The prefix transform saved **28.9 ms of complete detector CPU per dual visit** in the median of 80 paired comparisons, an **8.2%** reduction. The two arms used the prepared coarse grid, row-wise peak selector and the same conditioned and GLRT refiners. All 160 timed detector calls reproduced the complete ordered public payload and archived factor projection from the installed capture producer. The test passed the preset 15 ms CPU gate for whole-waveform replay. [Timing and parity summary](summary.json) · [Measured stages](stage.pdf) · [Protocol](PROTOCOL.md)

| Capture | Original → pruned CPU median | Median paired CPU savings | Median paired wall savings |
|---|---:|---:|---:|
| DS26-0237, lower | 403.0 → 355.0 ms | 34.5 ms (9.2%) | 33.4 ms |
| DS29-0082, upper | 493.3 → 453.7 ms | 31.4 ms (6.4%) | 29.9 ms |
| DS29-0174, upper | 293.8 → 267.0 ms | 23.2 ms (7.6%) | 12.8 ms |
| DS29-0519, lower | 309.1 → 286.3 ms | 27.7 ms (8.1%) | 19.9 ms |

Each case contributed four saved dual-receiver visits and five alternating repetitions per arm. The pooled paired wall median was 24.7 ms (7.1%). Wall differences spanned −374 to +841 ms on the shared host, and CPU differences spanned −60.6 to +108.5 ms. Per-case reductions refer to medians of paired individual differences. The axis ranges in the stage chart show observed min and max. [Frozen panel and runtime identities](input-lock.json) · [Per-call measurements](stage.csv) · [Case and visit summaries](stage-summary.csv) · [Stage artifact seal](stage-figure-lock.json)

## Which FFT work the prefix removes

The 10 MHz detector uses 150 alternating pilot symbols with 44 samples each, 14 or 15 supported frames per fine search, and a 20,000-point FFT. The genuine searches requested contiguous prefixes of 161 or 321 bins on the 500 Hz grid. The pruned transform performs the first three capture-era mixed-radix passes in binary64 and keeps only those fourth-pass output branches that feed the requested prefix. The last two passes compute only the zero-frequency sum in each remaining radix group. Absolute-CFO derotation, per-frame normalization, all requested fine scores and the capture producer's quadratic interpolation remain in the scoring path. [C kernel](../../../../tools/pipeline_eval/variants/fine_search.c) · [Capture adapter](../../../../tools/pipeline_eval/variants/fine_search.py) · [PocketFFT source](https://github.com/mreineck/pocketfft/blob/cpp/pocketfft_hdronly.h)

Alternate FFT lengths, pilot geometries, and runtime arithmetic that fails the startup check dispatch to the original scorer. The staged native binary is 19,808 bytes and uses 1,037,040 bytes of private array workspace. The cache of exact base rotations is bounded by 6,758,400 bytes of array payload, and the panel used 19 or 20 entries per worker. The complete worker high-water RSS was 179–200 MiB, including archive decoding and the common detector workspace. The implementation comprises 155 C lines and 130 Python lines. [Component tests](../../../../tests/pipeline_eval/test_fine_search.py) · [Resource counts](summary.json)

## The archived factors include rejected candidates

Every complete call preserved all 256 ordered public candidates on the unique visits, including 207 that failed the integer margin gate. The archived projection preserved 32 receiver rows containing 163 candidate factor records, including 116 that failed the fractional gate. The panel covers three producer roots, both edges, four genuine negatives, single-lane positives and near-gate visits. The smallest fractional margin distance from the 0.025 gate was 0.00267. The separate scoring audit matched all 312 score tuples through 4,369 frame transforms and 1,362,129 requested frame bins, with zero fallback calls. The closest genuine fine-score competitors were separated by 7.32 × 10⁻⁷. [Per-visit score and gate audit](summary.json) · [Qualification seal](qualification-lock.json)
