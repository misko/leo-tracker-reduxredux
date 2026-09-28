# Calibration nomination diversity after catalogue grouping

This read-only audit groups track-candidate hypotheses by catalogue number before counting
satellite alternatives. It uses only the 12 calibration lanes and their reception forecasts. Log
prior masses are combined with log-sum-exp and renormalized over retained nominations; no outcome,
fit, held window or decoded identity is used.

Seven of 12 lanes have only one catalogue with conditional prior mass at least `1e-6`. The other
five have two or three. Catalogue-grouped effective counts range from 1.000 to 3.000. Thus the
track-hypothesis count overstates satellite diversity in several lanes: two lanes contain six
finite track hypotheses but only three distinct catalogue numbers, and most lanes are effectively
single-catalogue under the frozen conditional prior.

For each distinct catalogue the audit forms the first-to-last reception LOS delta, averaging only
duplicate track hypotheses for that same catalogue by their conditional prior. It then reports
prior-pair-weighted angular disagreement between different catalogues. The five lanes with
material alternatives have weighted mean delta-direction disagreements of 28.7, 44.9, 54.5,
74.9 and 76.3 degrees. This shows that some calibration lanes contain genuinely different nominal
direction trajectories, but it does not identify which catalogue is correct.

Angles from lanes with one material catalogue must not be interpreted as directional diversity.
Their total prior mass on distinct-catalogue pairs is tiny, in several cases below `1e-40`; the
full-vector angle can remain numerically defined because negligible alternatives have finite
mass. The artifact exposes `prior_pair_mass` beside every angle for this reason.

The endpoint east-delta sign, directly relevant to the signed-east tilt feature, is less diverse
than the full-vector angle. Ten lanes put essentially all catalogue prior mass on positive east
delta, one puts all mass on negative east delta, and one splits mass equally between positive and
negative. Full-vector angular disagreement therefore must not be described as equivalent
east/west ordering information.

These are conditional training-prior alternatives, not calibrated satellite probabilities or
decoded truth. The audit supports the narrower conclusion that nomination ambiguity is uneven:
five lanes offer material between-catalogue directional alternatives, while seven effectively do
not. Any geometry-identifiability summary should count grouped catalogues rather than duplicate
track hypotheses and should keep this limitation separate from within-catalogue motion.

The corrected machine artifact is
[nomination-diversity-corrected.json](nomination-diversity-corrected.json), with frozen command and
input hashes in [nomination-diversity-corrected-launch.json](nomination-diversity-corrected-launch.json)
and completion hashes in
[nomination-diversity-corrected-receipt.json](nomination-diversity-corrected-receipt.json). It ran
in 0.21 seconds under the 30-second, one-thread, 4 GiB bound. The initial artifact and its exact
hash-matching source are preserved with the `nomination-diversity-initial-*` prefix; that version
did not suppress a misleading weighted median when total pair weight underflowed to zero and is
superseded by the corrected artifact.
