# S05: the 63387 family needs a separate model check

The largest individual linear-fragment preferences for the evaluation position
include three nominees for NORAD 63387 that fail the baseline residual gates.
They must not be promoted to accepted associations merely because they improve
position error. The family identity itself remains a hypothesis.

At the original blind c0 solution, the RX2 CH2, CH3, CH4 and CH7 nominees have
residual slopes of approximately −21.31, −20.59, −21.02 and −21.37 Hz/s.
They overlap near 280–294 seconds into the scan. The CH5 nominee has a larger
−48.95 Hz/s slope and needs its own identity or fragment-integrity check.
At evaluation GPS, after recalibrating with the same curved observations only,
the first four slopes remain about −18.53, −17.76, −18.10 and −18.34 Hz/s.
Changing position alone therefore does not remove their systematic residuals.

The curved nomination population for this satellite consists of three fragments
on RX1 CH2 and CH7, totaling 98 points. Their residual slopes range from about
−2.33 to +3.09 Hz/s at the blind solution. This is not sufficient evidence to
assign the late RX2 error to either the satellite or the receiver: time,
receiver and satellite support are confounded. The retained causal element set
is about 25.5 hours old at this observation; age alone does not establish an
orbit maneuver or TLE error.

The next useful tests are:

1. Compare unrelated curved satellite families on RX2 over the same late interval
   to distinguish a receiver term from a satellite-specific discrepancy.
2. Inspect the 63387 candidates against the first following TLE as a postfit
   diagnostic, while keeping every inference prior causal.
3. Revisit causal orbital covariance, preserving correlations between phase,
   mean motion and orbit-plane errors rather than widening independent priors.

[Numerical diagnostic](S05_63387_diagnostic.json) records residual quantities
at both positions. Its slopes are descriptive least-squares diagnostics; no
linear fragment was used to estimate calibration. This companion is a postfit
investigation and is not one of the frozen renderer replay products.
