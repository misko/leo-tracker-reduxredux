# Independent final-prototype control screen

The frozen primary full-window point passes the practical exploratory RF screen:
48/48well-timed strong trials are admitted within500Hz, with no admitted>1kHz
error in any strong stratum. The±3.5sample stress cohort also admits48/48within
500Hz. No source or reference-time implementation error was found in the audit.

The well-timed strong cohort's mean earlier CFO error is1157.32Hzand its mean
measured error176.80Hz; only5/48outputs have zero innovation. This tests actual
frequency information beyond accurate carry. Stress error is186.57Hz. These
results do not calibrate fine covariance: the same443.892Hzdonor-centered FFT
grid remains. Three identical method evaluations in these controls are paired
copies on the same target, not three independent experiments.

All four Gaussian null strata (edge×identical/distinct companion points) have
0/32primary admissions, exact one-sided95%upper0.089368, meeting the frozen
practical screen. All32wrong-symbol-roll controls are rejected by every method.
This remains a conditional synthetic model, not deployment FAR or a whole-panel
family-wise bound. Companion methods and their union are reported separately;
operational admission is never a target-selected union.

Reference conventions match the new waveform: carrier and quadratic arrival
clock are defined around dt=t−.010, with midpoint timing epoch4321.25. Earlier
and target midpoint counters differ by exactly0.354s. The consistent linear
point equals round1primary.full.epoch_samples, the quadratic alters only timing,
and the descriptive legacy point retains its separate extra advance. The
scorer passes each epoch directly without another timing-rate shift. Nominal
midpoint remains an approximation to the actual sample-weighted measurement
time; no definitive retrospective bug claim follows from this convention.

All576earlier-only forecasts replay exactly:289quadratic,164fallback,123no donor.
CFO/rate and primary branch are unchanged in all methods; all donor native
support/generation and origin/midpoint references pass. The first independent
least-squares audit incorrectly mixed fractional phase with a trillion-sample
absolute counter before subtracting it. The producer already subtracts exact
integer counters first. Correcting that audit arithmetic removed its numerical
discrepancy; a new large-origin invariance test passes. No producer or scientific
output was changed.

Exact compact records: `prediction_audit.json`, `control_audit.json`. Development
raw replay remains a separate gate; no held-validation target or geography has
been opened in this branch and no position/promotional result follows these
synthetic controls.
