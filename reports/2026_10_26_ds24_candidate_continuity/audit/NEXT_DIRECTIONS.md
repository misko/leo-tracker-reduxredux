# What this iteration changes

The strongest result is a limit on interpretation. The [recorded inventory](../recorded/FINDINGS.md)
finds zero persistent positives among 117 original owners under its frozen
nearby-alternative rule. The [synthetic prototype audit](prototype_terminal.json)
shows that retaining candidate alternatives can recover source-proximate paths
which maximum-margin selection discards, but CFO-only and epoch+CFO select the
same candidates in all eight lanes. The [single-source control](single_application_terminal.json)
also produces secondary coherent paths from one injected emitter. Neither
peak multiplicity, path continuity nor larger candidate counts establishes
additional independent physical information.

The accumulated position studies support a substantial conditional tradeoff
between position, satellite timing/shape and receiver nuisance parameters.
They do not yet identify one universal cause of field error. A restart result
constrains local minima for the tested model/cases; it does not rule out wrong
assignments or another model's minima. The fast studies do not independently
vary sample rate, calibrated receiver baseline or bearing, so they cannot
attribute the remaining error to those variables. Conditional information
gains and occasional unqualified position improvements remain distinct from
achieved, qualified localization accuracy. Conservative admission guards are
necessary here; their rejection alone does not prove physical mismatch or
that the guards are physically calibrated.

The highest-value next observable check is whether the exported window
midpoint is the correct effective time for this CFO estimator. The public
port assigns a midpoint, while the deployed scorer selects epoch-dependent
complete frames and 64 pilot symbols, sums coherent power within each frame
and discards inter-frame common phase. Acquisition plus a gridded residual
is not automatically instantaneous CFO at that midpoint. First derive the
actual averaging support, then use a small predeclared known-chirp/epoch
closure to test that law. This is different from fitting a clock-scale or
timestamp offset against GPS. It should produce a measurement operator or
a bound, not a freely fitted timing correction. At 200 Hz/s, moving a time
tag anywhere within a 20 ms window changes isolated instantaneous CFO by at
most 4 Hz (only 2 Hz from midpoint to an endpoint). The known-single-source
main paths already have about 16.5 Hz graph RMS, so a time-tag correction
alone cannot remove that toy error either. Acquisition/refinement response
and quantization must be part of the observable check. Interference and grid
locking can also invalidate the instantaneous-CFO
interpretation. This narrow calibration is useful even though the deployed
template is not independent physical waveform authority; stop before a
position campaign if its measured effect is negligible.

Then use a small recorded-IQ diagnostic with the already demonstrated
historical replay authority to check whether that operator transfers to
recorded responses. Freeze a handful
of flagged windows and matched unflagged controls by RF metadata, then retain
the acquisition CFO, refinement residual, local epoch/CFO score surface and
all candidates for those exact native windows. These missing recorded fields
currently prevent the [gap readback](../grid/FINDINGS.md) from separating
acquisition differences from refinement/alias structure. Compare the saved
response against the one-source control without changing the detector or
path thresholds. A separate maximum is still not proof of a second emitter;
the decision is whether the proposed branch contains measurement evidence
beyond correlated alternatives of one peak. Stop if the recorded behavior
is explained by that ambiguity, or if the deployed response cannot be
reproduced. This is an upstream measurement test, not another orbit fit.

The next localization-facing test should use a genuinely available separate
whole owner or receiver/channel witness for a predeclared RF-selected family.
Predict that owner's complete observations from the original shared parent
with its own response excluded from calibration, noise and nomination.
Keep common radio, phase, physical-mode and owner-constant covariance;
compare a proper unresolved alternative. If no such witness exists, report
that prerequisite failure instead of converting a different label or reusing
the target as corroboration. Only successful independent predictive support
would justify a bounded matched-c position comparison with all original IDs
and baseline fallback preserved. It would still need broader-case validation.

More same-scan toy controls now have diminishing returns. Another seed or
looser persistence gate could improve an exposed example while leaving
source specificity and field accuracy unidentified. Stop repeating that
pattern, forced candidate retention, broad nuisance expansions without a
measured mechanism, or ever more precise integration of irrelevant losers.
The current zero-positive recorded result should remain a stop, and the
single-source false-extra-path example should remain a negative control for
any future candidate-continuity implementation.
