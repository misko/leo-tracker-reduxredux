# Higher-rate FFT coarse-proposal integration

This research build integrates the reviewed V5 overlap-save bank into the
original conditioned-CZT full-search baseline. It keeps the direct FP32 coarse
path at 2.5 MS/s and uses FFT lengths 128, 128, and 256 at 5, 7.5, and 10 MS/s.

The FFT grid is proposal evidence. Before final peak retention, epochs above
the current separated top-eight boundary and their linear neighbours are
recomputed with `coarse_fp32_cell`, after clearing their accumulator and
support. The threshold is iterated. Allocation, nonfinite arithmetic,
unsupported rates, invalid FFT geometry, and an ambiguous final selection
boundary fall back to the complete existing direct grid. The
`128*FLT_EPSILON` guard is an engineering threshold, not a formal error bound.

Input FFT buffers are block-sized and kernel spectra are cached for each
symbol while it is processed. No filters-by-positions array is allocated.
The symbol, frame, block, and output loops preserve direct symbol/frame/epoch
addition order at the accumulator boundary. FFTW planning and kernel setup are
currently inside the reported coarse CPU interval.

`build.py` makes isolated source-receipted host or ARM builds from the named
conditioned-CZT baselines. `test_fft_integration.c` covers all rates, randomized
complex partial windows, full zero windows, direct retained-candidate parity,
and a forced allocation-style fallback path.

This is an integration candidate. Full host cohort and ARM window timing are
acceptance gates; standalone microbench gains do not establish a full-search
speedup.

The completed evidence accepts this proposal only for further higher-rate
qualification: the 5/7.5/10-MS/s ARM probe set improved by 1.1671x, 1.4249x,
and 1.6382x with identical candidates. The combined binary is rejected at
2.5 MS/s, where final ARM V5 measured 0.9813x the conditioned-CZT baseline.
The host704 run provides exact candidate-object parity but is not ARM timing.

Exact archived sources and build receipts are under `builds/`: ARM V4 is the
measured all-rate build, ARM V5 restores the original 2.5-MS/s call site, host
V6 is the final host build, and host ASAN V3 is the sanitizer-qualified FFT
source before that call-site-only change. Executables remain in their
source-receipted `/var/tmp` build locations.
