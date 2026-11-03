# Prospective pilot/GLRT fallback on two exposed DS11 scans

Use the already selected scan0/NORAD65512 and scan16/NORAD67103 training rows,
with both original pilot windows. No new source selection, RF collection or
offline orbit data. Preserve every original localization observation and mask.
This is a new estimator experiment; the failed original scan16 gate stands.

Freeze this rule before measuring scan0 split-frame stability or fitting any
new positions: apply a pilot correction only when its full estimate and both
alternating-frame-group estimates are finite, strictly inside the original
search boundary, and the two group estimates differ by at most100 canonical Hz
(native difference times11.2GHz/actualRF). Otherwise use the original GLRT
frequency and timestamp for that observation. The100Hz threshold matches the
existing position likelihood's scale; it is an engineering heuristic, not a
calibrated confidence bound. Do not tune it, add a coherence cut, or change
arms after viewing these results. Report acceptance counts and reasons.

All stability records must be complete and replay the frozen full estimates;
missing records invalidate the experiment rather than silently authorizing
fallback. Obtain the scan0 diagnostics using the exact scan16 stability assay,
one180-second worker on its111 saved excerpts. Bind all artifacts and code.

Accepted corrections use nominal eight-frame FFT centers and the verified
per-observation interpolation over the original causal state bank. Fallback
rows use original times. No change to RF aliases, other tracks, held values,
likelihood, candidate bank, per-track CFO profiling or reference. Use timing
bounds[-4.995,4.995]seconds to remain inside the original bank.

For each of two arms and two scans, use original IID plus the three generic
starts:16 fits total,90seconds each, maximum three single-thread workers,
nice19, no numerical retry or recovery. Require the original endpoint's exact
score replay and fresh numerical qualification before launching. Preserve all
attempts. Seal highest-qualified-training-score selections for both arms on
both scans before evaluating geography. Report unavailable comparisons when
coverage or qualification fails; do not substitute a geographic winner.

The long arm is the existing lead. Directional replication requires its
reference error to be lower than original IID on both scans with complete
measurement coverage and qualified endpoints. Report the short arm regardless.
Two exposed scans do not demonstrate corpus-wide or deployment improvement;
passing this check only supports a separately planned wider confirmation.
