# Guided frequency-support boundary: numerical fix qualification

The reference-point diagnostic found a valid application frequency residual
only about 2.8e-9 Hz beyond the native API's half-symbol-frequency bound.
The diagnostic's precheck skipped that point; a subsequent direct call to the
unchanged C API also returned no observation. Advancing the expected physical
CFO by one floating-point step toward the scoring CFO still returned none.
Both direct outcomes are retained in
`../native_reference_points/boundary_api_audit.json`.

## Fixed change

Allow an explicit 1e-6 Hz numerical tolerance on the input residual-support
comparison only. This is the existing reference-point diagnostic's absolute
frequency-reproduction tolerance, far below its 8 kHz physical identity gate.
Do not perturb, clamp, wrap or replace the caller's scoring or expected physical
frequency. Preserve the independently measured physical CFO and the original
8 kHz innovation rejection, timing/support/fractional gates, and margin >=0.025.
The tolerance permits a call to be scored; it does not force positive status or
choose a frequency alias.

Build the change as a new research library with a separate source/build receipt.
Reuse the original numerical kernels. Do not edit frozen TG11 or reference
checkout sources, libraries, previous receipts or golden fixtures. Component
tests must compare ordinary guided and blind science with the original, check
rejection beyond the tolerance, and show that the physical innovation gate
still rejects an incorrect expected frequency even when API admission succeeds.

## Fixed evaluation

1. Reuse all 42 point coordinates in
   `../native_reference_points/source_lock.json`, including the numerical
   boundary and the genuine measured-frequency disagreement. Call both the
   original and new guided APIs directly, without the diagnostic runner's
   support precheck. Preserve both results, status flags, score/physical errors,
   and pair assessment against the fixed reference coordinates.
2. Reuse all 42 legacy control/sequence occurrences from the frozen tradeoff
   adapter, both receivers. Run the original and new engines through separate
   instances of the unchanged causal tracking controller. Check all injected
   truth and known negatives, and compare activity and selected identities.

Freeze the new engine/build and owned tests, runner/tests, this design, the
original point lock/result and all its locked files, and input memberships
before outcomes. The supplemental boundary audit is pinned as prior evidence.
There is one 120-second budget, one DSP campaign, CPU 0, and numerical threads
one. Preserve full outcomes on science failures. Source/geometry/runtime
failures produce incomplete evidence; never retune the frozen fix to pass.

Use development IQ only. Check raw immutability and source hashes after the run.
No full application search rerun, validation generation, holdout access, RF,
QNAP writes or production changes occur. Record point and control timings as
diagnostic measurements only. This experiment qualifies the numerical API fix;
it does not measure a causal rescue detector, broader accuracy or end-to-end
10x speedup.
