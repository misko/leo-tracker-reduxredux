# CFO precision: source-level feasibility

No IQ, recording replay, model evaluation, position references or reserves were
accessed. This is an unbound research proposal, not authorization to run a new
experiment or modify persisted contracts.

**A research sidecar is feasible, but duration alone cannot establish that the
125 Hz floor dominates acquisition variance.** The estimator combines power
across frames, not coherent phase over the full 20 ms window. Treating 20 ms as
one coherent frequency baseline would substantially overstate its information.

## Exact local implementation and replay route

- The Python original-anchor scorer is
  [conditioned_glrt64_score](../../src/leo/analysis/starlink/pilot_methods.py:726).
  Its [workspace construction](../../src/leo/analysis/starlink/pilot_methods.py:1080)
  retains complex exact/control symbol correlations, times and valid-support
  flags. Lines 1140–1182 show template energy, received energy, acquired-CFO
  derotation, fractional sampling and normalized symbol powers. Received energy
  contains signal and interference; it is not an independent noise estimate.
- [The GLRT](../../src/leo/analysis/starlink/pilot_methods.py:1222) computes
  `sum_frame |sum_symbol z * exp(-2*pi*i*f*t_relative)|^2`, then divides by
  `sum_frame (sum_symbol |z|)^2`. This coherent ceiling is data dependent and
  is not a Gaussian noise likelihood normalization. Exact-minus-control margin
  therefore cannot be substituted for SNR or precision.
- The native implementation's
  [conditioned spectral reduction](../../src/leo/analysis/native_glrt/kernel/private/native_presence/presence.c:653)
  accumulates frame spectra and coherent ceilings; lines 789–814 show the
  512-bin maximum and normalization. The
  [reproducible builder](../../src/leo/analysis/native_glrt/README.md:126)
  (`leo.qualification.arm_glrt_release`) records compiler, flags, source,
  FFTW and output hashes. Historical research also used
  [tools/native_presence.py](../../tools/native_presence.py:272). These are
  different build routes: bind the actual backend/build rather than calling
  any current native binary historically identical.
- [128 evaluate.py](../2026_10_09_position_error_iter128/evaluate.py:34) already
  reconstructs the original epoch/acquired CFO/fractional anchor, supports
  2.5 and 10 MS/s via the original Python scorer, checks exact/control/CFO parity,
  then extracts symbols 2..65. Its private workspace access is acceptable inside
  a source-bound research adapter; it is not a new public persisted contract.
  [128 run.py](../2026_10_09_position_error_iter128/run.py:145) uses the public
  read-only `AdaptiveHopIqStore` port. The
  [134 EventReader](../2026_10_10_position_error_iter134/replay.py:23) explicitly
  maps sparse event IDs to public visit ordinals. A future replay must preserve
  that correction, original observation membership and original admission.
- [125 refine.py](../2026_10_09_position_error_iter125/refine.py:29) already
  differentiates the exact normalized spectral polynomial analytically. Its
  derivatives are per **bin**, so frequency curvature needs division by
  `Delta_Hz**2`. This supplies inexpensive peak shape, not calibrated variance.

## What a sidecar can and cannot contain

Without changing any published contract, a separately versioned research file
can bind each original observation ID, input/window hashes, backend/build,
template, sample rate, acquisition anchor and unchanged admission to:

- actual admitted symbol times/masks and frame counts;
- exact spectral value, first/second derivatives and neighboring peak evidence;
- sufficient complex correlation/energy summaries for an explicitly declared
  noise model, plus an unavailable reason when it cannot be supported.

The present workspace does not identify physical signal-on/off support: its
validity mask describes available samples and interpolation guards. Nor does
the persisted window metadata retain the complex correlations or calibrated
noise covariance. Exact information cannot be recovered from metadata alone.
Fractional interpolation correlates noise; template mismatch and interference
can invalidate an independent white-noise approximation. Reconstructing the
original workspace also does not recover uncertainty in the acquired epoch or
acquired CFO automatically.

## Cheap analytical gate before any positioning work

For independent complex symbol noise of variance `nu`, a correct single-tone
model and a separate unknown phase per frame, use the within-frame expression

`I_f = 2*(2*pi)^2 * sum_frame,sum_symbol (|mu|^2/nu)*(t-tbar_frame)^2`.

This is a conditional ideal-model information calculation. It must be Schur
projected further for any additional estimated nuisance and adjusted for actual
noise covariance. Across-frame time gaps do not enter as a coherent baseline.

For an ideal approximately uniform 64-symbol block, `T` is about 0.28 ms
(63 gaps of 4.4 microseconds), and with total integrated symbol SNR `R` summed
over frames, `sigma_f^2` is approximately `6/((2*pi)^2*R*T^2)` in that model.
Consequently, ideal standard deviation below 125 Hz requires total integrated
SNR on the order of 10^2; substantially smaller variance requires substantially
larger SNR. This is an illustrative analytic threshold, not a measured SNR or
predicted error for these recordings. Partial symbol support shortens the useful
baseline and may introduce competing peaks rather than a wider single peak.

Thus high-SNR fully supported windows may be floor dominated, but neither a
20 ms nominal duration nor a passed margin proves it. The source-only gate
does **not** justify assuming most observations need downweighting. First
validate a noise/curvature interpretation on unchanged estimator support using
bounded synthetic signal/noise tests, including interpolation and partial
support. If a later authorized acquisition-only replay finds almost all
calibrated uncertainties below 125 Hz, stop the proposed downweighting route:
`max(125^2, sigma_i^2)` would be nearly a no-op. If uncertainty is not calibrated,
report unavailable rather than invent precision from margin or profile shape.

Changing the estimator's mean through sub-bin refinement has already been
studied; this proposal must not rerun it under a different name. The separate
question is whether demonstrably weak measurement information exists often
enough for a conservative, globally fixed weighting rule to matter. No expected
position gain, exact per-window sigma or embedded runtime claim follows from
this source review.
