# Shared-slope shadow: first chronological DS7 recording

Population is fixed before fitting: `single-001`, the first row of the sealed
full88 joint request. Keep its frozen joint position/timing and all eligible
tracks, nominees, masks and frequency units. This is a reused development record,
not a new confirmation panel. No geographic score is computed.

Fit one additive native-Hz/s slope shared by both software receivers and all
tracks in this capture, as a statistical nuisance only. Its exported frequency
column is `(11.2 GHz / actual RF) * capture-relative time_s`, using a common
capture origin rather than per-track mean times. Refit the existing stationary
per-track/per-nominee offsets on training observations only. Retain the full
visible candidate mixture and existing offset prior. No slope prior or frequency
gate is introduced. No hardware-calibration interpretation is allowed.

Optimize training mixture score from starts 0, -2 and +2 native Hz/s using the
analytic full-mixture slope derivative. Use L-BFGS-B with 100 iterations and
300 function evaluations per start, gtol1e-6 and ftol1e-12. Perform all three
predeclared computational regimes: bounds ±20, bounds ±40, and no bounds.
Select the best converged training score within each regime. These bounds are
computational choices, not physical limits. Preserve every optimizer receipt.

Primary comparison: fitted ±20 regime versus exact zero-slope replay on frozen
held predictive density. Report every track, candidate-weight movement, MAP
changes and effective candidate counts. Fit held outcomes nowhere. Widened and
unbounded regimes are sensitivity checks; do not choose the winner by held score.
Verify zero replay against the previous fixed-position audit and central finite
differences of the full training mixture at -0.5, 0, +0.5 and the selected slope.
Report fixed-position profile curvature without treating it as joint position/
nuisance identifiability. Geographic adoption still requires that joint check,
multiple chronological transfer records and independently justified calibration.

One run, 300 seconds, 4 GiB, one numerical thread, nice19. Bind all source,
tests and input hashes before launch. Preserve partial optimizer terminal output
if the run fails. No IQ processing, propagation, RF collection or QNAP mutation.
