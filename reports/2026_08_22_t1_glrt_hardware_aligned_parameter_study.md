# T1 GLRT hardware-aligned search parameter study

Date: 2026-08-22

Status: qualification report; exact kernels approved for deployment, search parameters unchanged

## Decision

Deploy the mathematically equivalent FFT GLRT64 and fine-CFO transform dispatch. Keep the current Standard and Research search parameters for now. The radix-2 profiles are useful research variants, but they change the sampled CFO lattice and therefore cannot be treated as a transparent implementation replacement.

This leaves one public GLRT64 method in each lane. Direct and FFT calculations are implementation backends of that method, not additional scientific GLRT flavors.

## Bounded evidence

The benchmark reread 50 immutable 20 ms probes from `cap-20260821T201522-841b2a20e151` `stream-0/RX1` using 8 worker threads. Each timing is the median of 3 warmed repetitions. The source recording was read-only; no RF was collected. The three fixed windows are the transition, old-gap, and steady-P3 windows from the preceding T1 study.

The fixed piecewise-linear frequency reference is applied only after each independent probe search. A hit means a margin-qualified candidate lies within 500 Hz of that diagnostic reference; it is not a calibrated false-alarm probability or identity claim.

## Equivalent kernel replacement

| Lane | Direct oracle wall | Exact dispatch wall | End-to-end speed-up | Max winner CFO delta | Max margin delta | Winner epoch changes |
|---|---:|---:|---:|---:|---:|---:|
| Standard | 2.749 s | 2.511 s | 1.09× | 5.82e-11 Hz | 1.36e-13 | 0/50 |
| Research | 20.564 s | 14.370 s | 1.43× | 7.28e-12 Hz | 3.62e-14 | 0/50 |

The direct oracle remains in code for unsupported geometry and regression checks. The dispatcher uses an FFT only when the CFO/symbol grid is exactly representable and the fixed cost model predicts a benefit.

## Parameter geometry

Only the fine-CFO step and its nearly equal radius change in the aligned variants. Coarse search, conditioned refinement, basin retention/separation, GLRT length, sample rate, and probe schedule remain lane-current.

| Profile | Fine radius | Fine step | Nominal bins | Fine DFT N | Radix-2 | GLRT N |
|---|---:|---:|---:|---:|:---:|---:|
| Standard current parameters, exact dispatch | 80,000.000 Hz | 500.000000 Hz | 321 | 5,000 | no | 512 |
| Standard radix-2 aligned | 79,956.055 Hz | 610.351562 Hz | 263 | 4,096 | yes | 512 |
| Standard finer radix-2 | 79,956.055 Hz | 305.175781 Hz | 525 | 8,192 | yes | 512 |
| Research current parameters, exact dispatch | 10,000.000 Hz | 100.000000 Hz | 201 | 25,000 | no | 4,096 |
| Research radix-2 aligned | 10,070.801 Hz | 152.587891 Hz | 133 | 16,384 | yes | 4,096 |
| Research finer radix-2 | 10,070.801 Hz | 76.293945 Hz | 265 | 32,768 | yes | 4,096 |

## Runtime and T1 result changes

| Profile | Wall | CPU | Wall vs lane current | Winner hits | Inventory hits | Strong probes |
|---|---:|---:|---:|---:|---:|---:|
| Standard current parameters, exact dispatch | 2.511 s | 8.953 s | +0.0% | 41/50 | 41/50 | 44/50 |
| Standard radix-2 aligned | 2.556 s | 9.009 s | +1.8% | 40/50 | 40/50 | 44/50 |
| Standard finer radix-2 | 2.530 s | 9.202 s | +0.8% | 40/50 | 40/50 | 44/50 |
| Research current parameters, exact dispatch | 14.370 s | 56.843 s | +0.0% | 42/50 | 42/50 | 44/50 |
| Research radix-2 aligned | 13.814 s | 55.304 s | -3.9% | 42/50 | 42/50 | 44/50 |
| Research finer radix-2 | 14.859 s | 57.841 s | +3.4% | 42/50 | 42/50 | 44/50 |

## Scientific deltas from current lane parameters

Candidate rows below are matched by probe, refined epoch, and nearest acquired CFO, rather than by rank. This keeps ordinary rank reordering from appearing as a large CFO change.

| Variant | Matched basins | Rank-slot epoch changes | Winner epoch changes | Median winner CFO delta | Max winner CFO delta | Max basin CFO delta |
|---|---:|---:|---:|---:|---:|---:|
| Standard radix-2 aligned | 500/500 | 295 | 1/50 | 43.9 Hz | 1.94e+05 Hz | 1.49e+05 Hz |
| Standard finer radix-2 | 500/500 | 246 | 0/50 | 19.6 Hz | 1.53e+05 Hz | 1.49e+05 Hz |
| Research radix-2 aligned | 1600/1600 | 537 | 0/50 | 2.83 Hz | 53.7 Hz | 1.98e+04 Hz |
| Research finer radix-2 | 1600/1600 | 375 | 0/50 | 0.774 Hz | 55.1 Hz | 1.99e+04 Hz |

## Hardware interpretation

- GLRT-512 and GLRT-4096 are already radix-2. The implementation now evaluates their identical uniform DFT grids with FFTs.

- The current 500 Hz and 100 Hz fine grids map exactly to N=5,000 and N=25,000 transforms. They are not powers of two, but PocketFFT still accelerates them; power-of-two geometry is an optional additional tuning dimension, not a prerequisite.

- N=4,096 is the smallest useful Standard radix-2 fine transform because the selected pilot samples span more than 2,048 sample positions. N=16,384 is the nearest practical Research choice to the current 100 Hz resolution.

- Conditioned refinement remains direct. Its small bin count does not repay the larger whole-frame transform. The 2.5 MS/s sample rate remains ideal because one 4.4 us OFDM symbol is exactly 11 samples.

## Recommendation

1. Release the exact dispatch under `standard-v2-production-2` and the updated science implementation digest.
2. Do not silently replace current Standard or Research parameters. Preserve the radix-2 and finer-radix-2 settings as named Research configurations until they pass full-corpus, threshold, and trajectory-level qualification.
3. Keep one public GLRT64 result contract. The direct oracle, exact FFT backend, and future hardware kernels should remain implementation choices selected by exact geometry and measured cost.

Machine-readable summary: [hardware-aligned-study.json](figures/2026_08_22_t1_glrt_hardware_aligned_parameter_study/hardware-aligned-study.json).

Candidate inventory: `hardware-aligned-candidates.jsonl.gz`.
