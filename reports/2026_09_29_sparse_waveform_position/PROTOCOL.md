# Sparse direct waveform correction: geographic shadow

Use all72 training-visit long-pilot corrections from waveform_uncertainty, with
the exact frozen18 tracks and four visits per track. No correction is propagated
to an unmeasured visit. Add residual_hz*11.2e9/actual_rf_hz to the existing canonical
dealiased observation, preserving its alias index. Verify native CFO conversion
and integer alias as in waveform_alias_audit. Do not modify held observations.

Fit all nine original eight-scan panels under the q020 unassociated-trend model.
Keep all original tracks, masks, timing grids and candidate banks. Compare cached
and corrected arms, both with three starts from the inherited solution and
east shifts[-.25,0,.25]km. Bounds E/N±12km, each scan time±5s. L-BFGS-B max100
iterations/160 evaluations, ftol1e-13/gtol1e-6. Select by training score only among
successful, non-boundary fits with projected gradient<=.01. Independently check
selected gradients against centered finite differences (maxdifference<=.02).
Retain nonconvergence and failed audits. Per-panel cap60sec, sequential one thread.

Replay original training and each held-track score before fitting. Report both
arms' error to the inherited exposed unsurveyed reference, position movement,
held log score with identical held measurements, and original-model held score
at the corrected position as an additional common-model diagnostic. No outcome
selects a correction, arm or start. Report correction coverage against all model
tracks and observations. This is a sparse local shadow, not full re-extraction,
global search, new-site validation or proof of independent sub-km accuracy.
