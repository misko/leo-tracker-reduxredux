# Frozen fixed-cone TRAIN generalization

Treat the six labeled cells from the prior pointing freeze as prespecified
cells. Deduplicate the identical coarse-rank-1 coordinate computationally and
retain both labels as aliases in output; never count it twice as independent
evidence. At
each cell evaluate the first six scans from both TRAIN groups at that identical
coordinate (12 scans total), selecting each scan's fixed candidate with the
original training-only Doppler scorer. Perform no geographic optimization or
candidate reselection from pointing outcomes.

Assign whole NORAD candidate IDs to five deterministic folds with seed
20260923; the same NORAD stays in one fold across groups, scans, cells, mappings,
and controls. For half-widths 10, 15, 20, and 30 degrees independently, fit one
common mount orientation on four folds by maximizing duration-weighted coverage
inside the fixed cone. Use nominal axes 20 degrees apart, shared tilt at most 15
degrees, one-degree tilt, five-degree yaw/tilt azimuth, deterministic first-grid
ties, and both receiver mappings. Freeze the selected orientation and report
duration-weighted held-fold coverage, support duration, track count, and NORAD
count. Never choose a width from position error.

Run 20 deterministic whole-track receiver-label controls, permuting within
scan and exact RF-lane strata while preserving every stratum's label counts.
Report unchanged strata and labels that move. Evaluate all four widths from the
same cached angle matrix. Fail explicitly on empty folds, missing candidates,
invalid receiver labels, or incomplete 12-scan cell support.

Coverage is a geometric concentration diagnostic, not calibrated RF gain,
visibility, detection probability, or evidence that an outside-cone track is
absent. The common holder orientation across recordings is an explicit
unchanged-holder assumption, not measured absolute mount calibration. Use no
truth, VAL/TEST, position fit, new RF, or geographic search.

Primary coverage is membership of each track's midpoint direction, weighted by
that track's full duration; this is a duration-weighted midpoint proxy, not
proof of whole-track visibility. At each training-selected orientation, also
report a held diagnostic requiring the sampled start, midpoint, and end
directions all to lie inside the cone, without refitting. This three-sample
diagnostic does not guarantee continuous visibility between samples.
