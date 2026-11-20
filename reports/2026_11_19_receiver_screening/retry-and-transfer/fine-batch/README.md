# Batch the original fine CFO search across frames

The four-frame FFT saved **24.68 ms of complete detector CPU per dual visit (7.24%)** in the median of 80 paired comparisons against the qualified scalar prefix FFT. It cleared the 10 ms and 3% CPU gates for a bounded complete saved-waveform replay. All 160 timed calls matched the installed producer's ordered public payload and authenticated factors. [Timing summary](summary.json) · [Stage chart](stage.pdf) · [Paired visit clocks](stage.csv) · [Qualification seal](qualification-lock.json)

| Saved capture | Median paired CPU savings | Median paired wall savings |
|---|---:|---:|
| DS26-0237, lower | 20.66 ms (5.55%) | 20.66 ms |
| DS29-0082, upper | 27.78 ms (7.53%) | 25.61 ms |
| DS29-0174, upper | 25.77 ms (8.73%) | 24.28 ms |
| DS29-0519, lower | 22.92 ms (7.97%) | 22.91 ms |

The pooled paired wall median saved 23.20 ms (6.70%), with individual differences from −234.16 to +246.05 ms. The two pooled unpaired wall medians were 280.84 ms for scalar and 302.82 ms for batched. The paired statistic compares the same visit and repeat amid variable host wall time. CPU differences ranged from −19.59 to +69.01 ms. The panel times resident IQ through the detector and factor projection. [Per-case timing ranges](summary.json)

## Fine and conditioned CFO work

Before batching, the port audits recorded a pooled median of 47.08 ms for fine scoring and 44.99 ms for the conditioned CFO stage per dual visit. Batching saved a paired median 14.19 ms (30.44%) at the fine port. The conditioned implementation and all its scored values stayed identical. Its clock varied between audit calls. The port audits ran separately from the timed detector comparisons. [Port timing rows](stage.csv)

The physical-probe audit observed 29 reuses of an epoch across 312 fine requests, with different frequency centers on every reuse. No fine `(epoch, center)` or complete grid repeated, including when a lane revisited the same IQ with fallback anchors. The conditioned stage repeated ten identical `(epoch, grid)` requests across 312 calls, all within one acquisition. All 312 conditioned proposals used the existing certified-winner route. The closest conditioned score gap was 1.31 × 10⁻⁷. Separate component controls verify the original fallback on an exact conditioned tie. [Per-probe dispatch and duplicate ledger](summary.json)

The full outputs retained 256 ordered public candidates, including 207 integer gate rejections, and 163 projected candidate factor records, including 116 fractional gate rejections. All requested fine scores matched the original full FFT across 4,369 frames and 1,362,129 frame bins. The conditioned score tuples also matched across 4,368 frames and 178,864 frame bins. The holds cover both physical receivers, both waveform edges, three producer roots, dual positives, single-lane positives, genuine negative visits and near-gate visits. [Frozen inputs](input-lock.json) · [Complete payload and numerical audits](qualification-lock.json)

## Four independent frame lanes

The candidate puts four independent frame transforms in the lanes of each AVX2 register. It preserves the original scalar prefix FFT's binary64 operation order for every frame and bin. Both arms keep the same prepared coarse grid, row-wise selection, pilot weighting, normalization, conditioned frequency search, and GLRT refiners. Each call scores 6,600 alternating pilot samples per supported frame and 161 or 321 contiguous bins. The 14- or 15-frame apertures fill four four-lane groups. The last group repeats one available frame in its unused lanes and stores only supported outputs. [Frozen protocol](PROTOCOL.md) · [Batch kernel](../../../../tools/pipeline_eval/variants/fine_batch.c) · [Runtime adapter](../../../../tools/pipeline_eval/variants/fine_batch.py)

The batch library is a 24,000-byte AVX2 build. Batched private array workspace rose from 1,037,040 to 2,957,040 bytes. The existing worker rotation cache held 19 or 20 reusable base rotations. High-water RSS was 192–213 MiB for workers containing both implementations, the original detector, replay decoding, and score audit. The candidate adds 131 C and 47 Python lines to the existing prefix source. [Resource counts](summary.json)

To stage it, call `fine_batch.build(build_directory)` once on the target host, then instantiate `fine_batch.FineBatch(library, acquisition)` once per capture worker. The startup check compares the scalar and four-frame kernels against NumPy Fourier arithmetic. A host without AVX2 can use the qualified scalar path. The capture adapter retains the installed scorer for unsupported waveform geometry or a failed arithmetic check. [Scalar qualification](../../pilot-search-and-region/fine-search/README.md) · [Hardware-marked component tests](../../../../tests/pipeline_eval/test_fine_batch.py)
