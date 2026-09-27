# Single-precision FFT qualification

This is a numerical detector variant, not an exact-equivalent optimization.
The frozen V4 outer detector and GLRT still use FP64. Only the FFT backend
changes; conversion into/out of FP32 is included in every call. Templates,
thresholds, candidate count, rank geometry and support remain unchanged.

Two separately built candidates are tested:

- `libfft32.so`: bounded built-in radix-2/5 FP32 transforms.
- `libfft32_fftw.so`: installed FFTW single-precision transforms with ESTIMATE
  plans. The server header and shared-library bytes are hash-pinned.

All allocation and plan construction occurs once at initialization. Every
candidate uses a separate library and build receipt; production/reference sources
are unchanged. There is no new runtime dependency in the application.

The transform tests cover random full-range CI16 complex input, radix-2 and
radix-5 lengths from 2 through 32768, aliased output reuse, zero, impulse, invalid
sizes and input preservation. Both relative L2 and normalized maximum error
must stay below 2e-6 against NumPy FP64. These 22 tests pass. This error bound
does not itself establish detector decision equivalence near the margin gate.

Whole-detector qualification uses the independently frozen FP64 V4 library as
the baseline, never an FP32 baseline compared against itself. The same 256
development receiver-visits are replayed with counterbalanced calls; fixed
pilot/noise/tone controls follow. Retention, changed rank/window selection,
timing/CFO drift, score drift and total cost must all be reported. There is no
automatic blind fallback hiding losses in this detector-variant experiment.
No threshold is retuned and no fresh holdout is opened.

Development results: both backends retain 36/36 reference positives with no
extras and identical fixed-control decisions. Relative to the packed FP64 blind
reference, strided built-in FP32 measures 1.393x and strided FP32 FFTW measures
1.505x CPU speedup. The maximum matched margin drift is 3.18e-8 and 6.12e-8,
respectively, with no rank/window changes. These ratios include the strided input
change and do not isolate FFT speed alone. Immutable results and source/runtime
hashes are in `../acquisition/results_fft32.json` and
`../acquisition/results_fft32_fftw.json`.

The measured blind-cost profile limits the impact of FFT work: the remaining
coarse correlations, conditioning, fractional scoring and rank folding still
cost time. A fast transform is not evidence of a 10x whole-detector result.

ARM qualification remains separate. A previously built research FFTW-float NEON
archive exists at `/var/tmp/leo-fftw-float-20260912/install/lib/libfftw3f.a` with
provenance in the deployment repository's
`reports/2026_09_12_adaptive_decimated_dwell/fftw-float-research-build.json`.
Its availability is not a timing result or a production dependency. The actual
ARM baseline/profile must be established before comparing target timings.
