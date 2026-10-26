# Independent allocation review

The strongest measured limitation remains weak separation of position from
orbital timing/shape, together with uncertain source membership and identity.
The [cumulative review](https://github.com/misko/leo-tracker-reduxredux/blob/0a13b253e6574ebc63b0817757df050be122709b/reports/2026_10_25_ds24_ambiguity_position/REVIEW.md) supports
this with conditional information and controlled experiments, not an observed
accuracy floor. Extra optimizer restarts and lower curve scatter have already
failed to yield reliable retained gains. All compared fast scans are 10 MS/s;
sample rate is not an identified cause. Feed separation is not a calibrated
bearing or independent station baseline.

This iteration closes a practical implementation issue: the exact geometry
cache preserves the original scorer at every frozen control and completes all
six position slots under the unchanged caps. It does not qualify the source.
The [terminal audit](position_terminal.json) keeps original support failures
and accepted-ID losses separate from numerical completion. Released geography
shows raw mixture gains of 82/119 m over no addition, smaller than the hard
label's 314/256 m gains on this exposed case. All operational errors remain
unchanged. This is no validation of the assigned identity or admission policy.

The 0015 restoration is informative about interpretation. With the full parent,
the target-fitted first physical-mode mean grows from approximately −0.64/−0.60
to −1.07/−1.13 prior units, while conservative residual gates still fail and
the target-fitted full-mode residuals pass. The old correction magnitude was
conditioning-dependent. This neither establishes a real orbit correction nor
falsifies 68904. There is no separate unused owner with its own explicit 68904
nomination in the audited persisted fields; missing complete feasibility lists
make this an availability result, not physical absence.

Original conservative gates remain necessary for the declared operational
comparison. They prevent a one-owner target from fitting a correction and then
using that correction as its own validation. Their preservation does **not**
prove that their thresholds, owner count, or omission of an unsupported mode
mean are physically calibrated identity tests. A source can fail an old-only
radio prediction because of conditioning, admissible nuisance uncertainty,
wrong identity, measurement error or composition. Conversely, target-fitted
low RMS alone cannot justify dropping these gates. Changing admission requires
predictive calibration or genuinely separate evidence, with the same shared
orbit/radio hierarchy and an unresolved outcome; it cannot be inferred from
either side of this residual comparison.

The highest-value mechanism still untested end to end is **winner-dependent
measurement and track composition at close sources or crossings**. Existing
curve-level inference fixes the detected measurements and owner memberships.
The current pilot-only detector control demonstrates such effects under its
declared synthetic law, but lacks realistic waveform/channel authority and
does not exercise tracking. The next bounded test should send predeclared trajectories
through actual detection and native-owner construction, alongside an oracle
measurement/ownership control. Keep every selected point, missed source and
false owner; compare frequency errors and whole-owner adequacy before any
matched-c position comparison. Stop at a failed waveform/background or tracking
contract prerequisite, or if the measured selection contrast is negligible.
Do not turn one imperfect waveform fixture into a field-bias claim.

The repeating trap is to keep refining evidence numerics or adding nuisance
freedom until a selected curve fits, then call either its fit or its rejection
an identity verdict. The cache has now made the declared ambiguity experiment
tractable; use its actual position and gate outcomes to decide whether it
deserves a frozen later-panel test. Do not reopen 0015 with another target-only
shape fit, repeat unchanged generic multistart/remeasurement, or launch a larger
campaign merely to collect more passing diagnostics. Conditional information,
finite-pool ordering, source adequacy and achieved geographic accuracy remain
four different claims.
