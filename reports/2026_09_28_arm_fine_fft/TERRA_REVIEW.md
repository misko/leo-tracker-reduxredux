# Fine FFT and coarse reuse review

This is a read-only review of the frozen `fine_scores` path in
`reports/2026_09_27_plutoplus_static_arm/optimize/work/goal40mag/src/native_presence/presence.c`
and the private FP64 implementation in
`reports/2026_09_28_arm_full_optimization/fft_full.c`.  It makes no claim
from a new run.

## Evidence correction from the primary agent

The recommendations below were written without incorporating two existing
implementation facts. The FP64 pruned backend has already been measured:
2,745.45 ms versus 2,740.62 ms for the unpruned optimized pipeline on matched
2.5 MS/s ARM probes. It is therefore not a demonstrated speed improvement.
Also, the active FP32 coarse implementation already computes rotated templates
and reference energies once in `coarse_fp32_templates()` during workspace
creation. That caching suggestion does not remove additional work in the
currently qualified path. Retain the geometry and qualification checklist
below as review material, not a new implementation recommendation. This turn
instead measures FFTW FP64 and separately investigates a guarded FP32 screen.

## Fine acquisition

`fine_scores` constructs one zero-padded, template-weighted input per usable
frame, then calls `leo_fft_forward_range`.  It consumes only `frequency_count`
consecutive circular FFT outputs beginning at `first_bin`.  The full-search
adapter currently ignores that interval and calls `leo_fft_forward`, so it
computes every output even though the following loop reads only the requested
ones.

The quality-preserving optimization is a **FP64 selected-output FFT**: retain
the same input, roots, direction, zero padding and output-bin convention as
`fft_full.c`, but recursively evaluate only the requested circular interval.
The existing private `fft_pruned.c` is the appropriate shape for this work;
its test compares selected outputs against the full transform.  Do not replace
this with an FP32 FFT, direct oscillator recurrence, or a changed fine grid.

The important geometry is fixed by the frozen constructor:

| sample rate | fine FFT size | bin spacing | active input (`w->n`) |
| ---: | ---: | ---: | ---: |
| 2.5 MS/s | 5,000 | 500 Hz | 3,333 |
| 5 MS/s | 10,000 | 500 Hz | 6,667 |
| 7.5 MS/s | 15,000 | 500 Hz | 10,000 |
| 10 MS/s | 20,000 | 500 Hz | 13,333 |

Thus each ordinary coarse-CFO refinement covers at most 321 500-Hz bins
(`coarse +/- 80 kHz` inclusive), rather than 5,000--20,000 outputs.  At
7.5 MS/s the transform length is 15,000, so the selected-output backend must
exercise the radix-3 path as well as radix-2 and radix-5.  A power-of-two-only
algorithm silently changes the 7.5-MS/s contract.

### Equivalence and guards

The selected transform is mathematically the same DFT, but a pruned recursion
can reassociate FP64 additions.  It should therefore be qualified as a
numerically bounded implementation, not asserted bit-identical.  Required
guards are:

1. Keep FP64 complex input, roots, arithmetic, and `-fno-fast-math`; use the
   full `fft_full.c` implementation as the oracle.  Test impulses, single-bin
   tones, random weighted inputs, wrapped intervals, and all four lengths.
   Compare every requested complex output with a scale-aware FP64 tolerance.
2. Verify the whole fine-score vector before selecting a peak.  The range call
   must zero cells from `used` through `fft->size - 1`, including when the
   caller's reusable buffer previously held another frame.  Preserve the
   circular bin order starting at `first_bin`.
3. Require `first_frequency / fine_step_hz` to be integral within a small
   FP64 tolerance and require every requested point to advance by exactly one
   FFT bin.  Otherwise use the full transform.  The frozen code's bin lookup
   uses `nearbyint`; a range implementation must not quietly round a non-bin
   grid differently.
4. Preserve all `frequency_count` values, not just a predicted winner.  The
   parabolic fine-CFO estimate reads `best-1`, `best`, and `best+1`; retain the
   frozen endpoint rule (no interpolation if the winner is an endpoint).  A
   clipped band and a circularly wrapped bin interval are both valid cases.
5. Qualification must compare retained-candidate identity, fine score vector,
   selected fine CFO, the three interpolation neighbors, conditioned CFO, and
   final exact/control GLRT.  A score-vector tolerance alone can miss a
   near-tied-bin rank change.

The current full-search code has already separated this port behind
`LEO_FULL_EXTERNAL_RANGE`; this makes an A/B build possible without changing
the frozen fine-scoring function.  Its FP64 selected-output test threshold is
useful for a unit test, but corpus parity must set the acceptance decision.

## Coarse work shared by overlapping windows

This reuse is already present in the current qualified FP32 path:
`coarse_fp32_templates()` runs during workspace creation and caches the
twelve-symbol reference energies and 11 CFO-rotated templates.  It is not an
additional optimization to pursue there.  The observation only applies to an
uncached FP64 path, if one is ever evaluated separately.

Do not initially reuse a single long-window power prefix by subtraction or
update correlation sums as a window slides.  `coarse()` currently constructs
each window's prefix in sequence and forms received energy from local prefix
differences; a global prefix changes rounding.  Sliding correlation updates
also change the reduction order and are exposed to candidate rank changes.
If pursued later, treat either as a new numerical port: retain a per-window
FP64 reference path, compare all 11x`w->n` coarse cells before peak retention,
and require retained-eight plus final-GLRT parity across all four rates.
