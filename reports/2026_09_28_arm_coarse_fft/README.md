# Shared-input FP32 FFT coarse-bank microbenchmark

See `PERFORMANCE_REPORT.md` for measured decisions and the remaining gates.

This standalone experiment tests whether one input FFT can be reused across
the 132 exposed coarse filters: 12 symbols by 11 CFOs. It does not alter the
detector or claim end-to-end equivalence.

The deterministic synthetic fixture provides 8,192 correlation positions from
centered complex-float samples, with extra input for the filter tail. Each
configuration compares identical templates and samples at tap
counts 11, 22, 33, and 44 with FFT lengths 64, 128, and 256. Filter spectra
are cached. Timings include input transforms, complex products, all inverse
transforms, magnitude, and accumulation into the production epoch-major
12-float grid. Template packing, filter transforms, and FFT planning are
excluded and planning time is printed separately.

The direct ARM baseline reproduces the qualified kernel: tap-major packed
real/imaginary templates, three four-CFO vectors, original multiply/add
grouping, two reciprocal-square-root refinements, epoch-major vector stores,
and the scoped `no-prefetch-loop-arrays` option. It retains the twelfth
lane's instruction shape but fills that synthetic lane with zeros. The actual
qualified kernel has a nonzero 480 kHz template in that unused lane; full
search reads only the first eleven CFOs. The FFT path computes only
the 132 exposed filters, so reported ratios include removal of that padding
work. Both paths add symbols in ascending order for every epoch/CFO cell.

The ARM FFT magnitude handles four adjacent epochs with the same reciprocal
square-root sequence. The scalar host fallback uses `hypotf`; host results
qualify indexing, overlap-save boundaries, and memory safety rather than ARM
speed. Random-grid normalized RMS errors are about 1e-7, with maximum
per-output normalized errors below 7e-7. Zero and impulse checks pass. These
metrics cover raw accumulated magnitude only; they do not establish detector
screen or candidate parity.

Host ASAN/UBSAN outputs are stored alongside this report. The current
source-receipted ARM binary is `/var/tmp/leo-arm-coarse-fft-v6/coarse_fft_bench`.
It is a no-argument
CPU-only benchmark pinned to CPU 0 and reports median process CPU time across
three repetitions. Production integration should proceed only if the ARM
measurement wins and a later real-grid prototype preserves candidates.

ARM v5, which uses explicit four-bin NEON spectral multiplication, measured
the best FFT size at each tap count as follows:

| Taps | Direct ms | FFT ms | Speedup |
|---:|---:|---:|---:|
| 11 | 127.332 | 154.262 | 0.8254x |
| 22 | 229.951 | 165.635 | 1.3883x |
| 33 | 332.957 | 174.019 | 1.9133x |
| 44 | 435.303 | 187.101 | 2.3266x |

Thus the microbenchmark still loses at the 2.5 MS/s/11-tap case and wins at
the three longer tap counts. These are isolated raw-kernel measurements, not
full detector speedups. V6 changes only the one-time plan mode from
`FFTW_ESTIMATE` to `FFTW_MEASURE` and measured substantially slower. V5 is the
selected microbenchmark candidate for further work; v6 is retained as a
rejected experiment. The top-level C source is v6; use the exact v5 source
snapshot under `builds/arm-v5/` to continue the selected version.
