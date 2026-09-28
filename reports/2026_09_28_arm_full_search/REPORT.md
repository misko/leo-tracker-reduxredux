# Full-search ARM qualification, 2026-09-28

This experiment restores the original eight-candidate acquisition and integer-epoch
GLRT in a private native research kernel. It is a correctness baseline and the
first optimization of that baseline, not a real-time deployment qualification.
The published two-candidate ABI and production analyzer are unchanged.

## Measured 2.5 MS/s ARM result

Saved IQ only on PLUTO+ `192.168.1.15`, pinned to CPU0. Four unique 20 ms
receiver windows: first metadata-selected lower/upper dwell, RX0 and RX1,
probe zero. Each window runs all eight original candidates; each timed run
is repeated three times. No radio capture or capture simulation runs alongside
this experiment. IQ is loaded into RAM before the timed kernel call.

| Method | Mean CPU time per 20 ms receiver window | Speedup | Windows executed | Candidates evaluated | Original positive hits | Hits recovered |
|---|---:|---:|---:|---:|---:|---:|
| Full FP64, insertion sort | 5,291.81 ms | 1.00× | 4 | 32 | 2 | 2 |
| Full FP64, stable merge sort | 4,459.50 ms | 1.19× | 4 | 32 | 2 | 2 |
| Full coverage, FP32/NEON coarse search + FP64 refinement/GLRT | 3,337.59 ms | 1.59× | 4 | 32 | 2 | 2 |

Counts refer to unique windows/candidates, excluding timing repetitions. Both
positive candidate hits occur in distinct positive windows, so positive-window
recovery is also 2/2. These two hits are far too few to establish an 80% or 90%
recovery claim across DS7. In both full-FP64 methods, all 32 candidate outputs,
including negative ones, agree with the frozen original within the documented
numerical tolerances.
Agreement is not bit-for-bit identity across Python and C.

The FP32 variant changes coarse scores, so it fails strict coarse-grid parity.
Its candidate identities and downstream acquisition/GLRT fields pass the same
tolerances on these four probes. Maximum coarse-grid drift is 2.84e-7; maximum
downstream score drift is 2.03e-15. `COARSE32_AUDIT.md` records Terra's independent
field-by-field audit. Near-tied coarse peaks may behave differently on other
inputs; this variant requires a much larger recovery evaluation before use.

Sorting improves runtime by replacing quadratic stable insertion sort with stable
merge sort, preserving original tie order and greedy separation against every
previously retained candidate. It removes no windows, CFO bins, anchors, frames,
or candidates. On the first optimized ARM probe, coarse search takes 2,344 ms,
acquisition refinement/verification 2,061 ms, and final GLRT 37 ms.
The NEON variant reduces mean coarse time to 1,214 ms while keeping every
original coarse epoch/CFO hypothesis and all eight candidates.

The measured full-search kernel is still far from real time. This prototype
executes individual windows; it does not yet schedule all 11 overlapping windows
per receiver in a 120 ms dwell. Multiplying the four-probe mean by 22 windows
gives about 98 seconds of CPU per dwell, an extrapolation rather than a measured
dwell runtime. The earlier 40% headroom result for reduced search does not apply
to this workload, and simultaneous capture headroom remains unverified.

## Evidence and reproducibility

The final full-FP64 implementation, including radix-3 support, also completed
16 metadata-selected probes on CPU0 across all four rates. This is one timed
execution per probe, not a repeated performance estimate. All 128 ordered
candidate evaluations match within tolerance, recovering 22/22 positive
candidate hits and 9/9 positive windows. The NEON variant has only the separate
four-probe 2.5 MS/s qualification above.

| Rate (MS/s) | 20 ms windows executed | Baseline positive windows / recovered | Baseline positive candidate hits / recovered | Mean CPU time per window |
|---|---:|---:|---:|---:|
| 2.5 | 4 | 2 / 2 | 2 / 2 | 4,462.91 ms |
| 5 | 4 | 3 / 3 | 6 / 6 | 11,835.74 ms |
| 7.5 | 4 | 1 / 1 | 6 / 6 | 22,311.00 ms |
| 10 | 4 | 3 / 3 | 8 / 8 | 35,418.31 ms |
| Total | 16 | 9 / 9 | 22 / 22 | — |

These are the first metadata-selected lower/upper inputs at each rate, receiver
0 and 1, probe zero only. They cover eight dwells, not their full 11-window
inventories. `ALLRATES_SUMMARY.json` and `results/fp64-allrates-arm/` preserve
counts, timing and receipts. The same 16 probes pass host and AddressSanitizer/
UBSan comparisons. Seven Python tests plus native retention and FFT tests pass.

- `results/fp64-insertion-arm/` and `results/fp64-merge-arm/` contain build receipts,
  execution receipts, raw native results, per-field comparisons and hit matching.
- `results/fp64-merge-host/` contains the same four-probe comparison on the host.
- `results/fp64-asan-host/` contains a successful AddressSanitizer/UBSan run of
  the insertion-sort implementation on those probes.
- `export_oracle.py`, `compare.py`, and `ORACLE.md` define the frozen Python
  oracle, source hashes, metadata selection and comparisons.
- `build.py` makes an isolated source snapshot and a static ARM binary with
  explicit CPU0 affinity. `arm_run.py` uploads only saved fixture files,
  verifies payload hashes and retains raw outputs before comparison.
- `full_search.c`, `full_search.h`, `test_retain.c` are private research code.
- `fft_full.c` extends the frozen radix-2/5 double-precision FFT with radix 3,
  needed by the 15,000-point fine search at 7.5 MS/s. `test_fft.c` checks impulse,
  known sinusoid and direct-DFT results. The original frozen source is unchanged.

The original larger comparison remains in `../2026_09_28_ds7_large_arm/REPORT.md`:
704 dwells, 15,488 original windows and 19,581 original positive candidate hits.
The reduced-window ARM method recovered only 499 individual hits there. Nothing
in this small correctness fixture supersedes that larger measurement.

`NOTES_NEXT.md` describes the next full-coverage optimizations: reuse absolute
coarse correlations across overlapping windows and prune unused fine-FFT output
work. The real-time/headroom goal remains open.
