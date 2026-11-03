# Availability-correct calibration geometry

The original two receiver donors precede the first DS11 target, but their fixed
geometry came from the pooled DS10 N24 fit. DS10 index 23 completed RF capture
at 1790686505057461572 ns and finalized at 1790686752093682239 ns. The first
DS11 target starts at 1790686628132675049 ns. Thus all RF samples precede DS11,
but one contributing finalized input was unavailable at the first target.
Earlier positioning experiments are orbit-causal retrospective experiments;
they do not prove end-to-end online calibration availability. Preserve them.

Refit the existing pooled DS10 q020, fixed-zero-height model using exactly the
23 inputs captured AND finalized before the first target. Verify each candidate
bank's orbit collection times precede its own recording. Use no DS11 observation
or reference position to fit, seed or select calibration geometry. Seed EN from
the existing available N8_0_h0 fit; populate timing seeds from available N8_0_h0
then N8_1_h0 sessions, and zero for others. Verify every seed panel's contributing
recordings also meet the same availability cutoff. Do not use N24 parameter
values even as initial guesses. One 90-second fit with the existing model,
optimizer and qualification gates. Preserve failure; no reference-based rescue.

This repairs the data-availability dependency, not historic software publication:
the resulting calibration remains a retrospective reconstruction from data that
was available by the stated cutoff. Subsequent multi-acquisition calibration
must bind this geometry and fit per-record timing from allowed data. Do not
reuse the old receiver coefficients with new labels or geometry without a new
frozen calibration/validation protocol.
