# Frozen staged full-FOV sweep through 90 degrees

Extend the audited staged cone-width experiment to full fields of view 10, 20,
25, 30, 40, 50, 60, 70, 80, and 90 degrees. Each half-angle is exactly half
the stated full FOV. Preserve the same five frozen cells, twelve TRAIN scans,
candidate caches, randomized training/held masks, 20-degree nominal axis
separation, 15-degree maximum shared tilt, and finite orientation grid.

For each cell and width independently, run the same single-pass sequence:
ordinary visible Doppler winner assignment with training-only CFO; freeze those
IDs; fit one common orientation across all twelve scans using the frozen IDs;
then refit once among ordinary-visible, RF-improving candidates inside the cone
at every training sample. Keep all eligible tracks in the occupied-second
weighted 800 Hz capped-loss denominator. Evaluate held rows only after freezing
CFO, orientation, and assignments.

Require exact 25-degree parity with the published staged result and reproduce
the prior 10/25/30 sweep. Report per-width, per-cell support tracks,
occupied-second support, training and held all-track losses, supported-only held
RMS, orientation, changed IDs, runtime, and across-cell ranges. Do not use the
width sweep for geographic selection or position-accuracy claims. Use no truth,
VAL/TEST, new RF, QNAP write, or deployment.
