# Fixed 160-call conditioned partial-burst screen

Predeclared before execution. No recordings, orbit geometry, positioning fits,
RF collection or receiver reference positions. Parent review/publication must
precede execution. No orientation extension or parameter retuning in this run.

- Actual source-built native `leo_presence_glrt`, default build flags; fixed
  acquired epoch 0, CFO 0 Hz, fractional offset 0. This bypasses acquisition
  and fractional-peak admission deliberately; it is conditional estimation.
- 2.5 MS/s, 20 ms, lower-edge exact pilot, zero transmitted CFO, frame starts
  rounded at 750 Hz as in `partial_signal.py`. Single monotone signal turn-off
  at **0, .00015, .001, .005, .020 seconds**; complete receiver noise remains.
- Signal multipliers **.25 and 1**, complex receiver Gaussian noise RMS **1**.
  Multipliers refer to the unchanged template, not asserted calibrated RF SNR.
  No total-energy renormalization for shorter bursts.
- **16 seeds: 120000 through 120015 inclusive**. Each produces independent
  real/imaginary standard-normal draws divided by sqrt(2). Reuse the same
  seeds across cutoffs/levels to keep noise exactly unchanged for comparisons;
  within-cell trials are independent, between-cell estimates are correlated.
- Exactly **5 × 2 × 16 = 160** native conditioned calls. No repeats, blind
  acquisition calls, extra CFO grid trials or noisy orientation sensitivity.
  One process; OPENBLAS/OMP/MKL threads all one. Failures preserve the exclusive
  start claim and prevent automatic restart; a failure is not a negative hit.
- The conditional margin rule is **exact-control >= .025**, matching the
  adaptive default. Do not impose the separate native host exact-score .175
  floor. No fractional-complete predicate is claimed by a conditioned call.

Hypothesis to screen: `P(margin pass | v,A,noise,correct seed) = v * P(pass |
v=1,A,noise,correct seed)`. Record the zero-occupancy false-margin rate too;
even a nonzero noise false-margin rate demonstrates that this unadjusted law
is not an exact total admission model. This is a small descriptive screen,
not a calibrated detection curve or a multiple-testing rejection procedure.
Report all cell counts and Wilson95 intervals, full residual CFO histograms,
individual scores/margins, native call time, build time and total elapsed.
No chosen CFO-accuracy cutoff or posthoc best setting. Any apparent agreement
only supports this fixed conditional simulation, not blind detection or
localization. A source-hashed JSON protocol pins these constants and scripts;
the compiled library hash and build receipt pin the executable realization.
