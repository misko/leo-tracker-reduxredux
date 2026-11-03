# Conditional cross-track lane-offset transfer

Use the3983 previously exported strong-candidate residual cases in all nine
eight-scan target panels. Verify their original evidence hashes. These cases
use training candidate-weight*signal-responsibility>=.5 and at least five
training observations spanning five seconds; do not add quality selection.

Convert canonical residuals to native Hz by actual_rf/11.2e9. Constant alias
branches differ between tracks, so compare offsets modulo P=1/4.4e-6 Hz. Estimate
each donor's offset from its arithmetic training-residual mean, then take a
deterministic circular L1 median per catalogue number. Estimate the shared offset
by the circular L1 median across catalogue numbers. Require at least three
distinct donor numbers; equal weight per number prevents repeated segments from
dominating. Exclude all donors with the target track ID or target candidate number.

Primary donors share recording, RX and exact actual RF. Also report opposite-RX,
same-recording/exact-RF transfer as a comparison, not an assumed negative control.
For each target, score median absolute wrapped residual on its held observations.
Compare with the target's own training-mean offset on exactly the same held data.
Report all unsupported cases, per-dataset/panel counts and paired errors.
Report training-only donor dispersion and target-offset disagreement descriptively.
No held values choose donors, offsets or thresholds. No position/reference changes,
geographic fit, new extraction or RF collection. One thread,120second numerical cap.

This is conditional on inherited training-derived location, time and candidate
hypotheses, not independent satellite identity. Failure would reject direct
offset sharing at these hypotheses, not all joint calibration/reassociation models.
