# Frozen TRAIN pointing generalization

Use the six locations, fixed Doppler-minimum candidates, durations, causal
states, and TRAIN-only support frozen by the pointing-cone pilot. Assign every
NORAD candidate to one of five folds with deterministic seed 20260923, keeping
the same NORAD in one fold across scans, locations, and controls. Fail if any
fold is empty.

For each location, mapping, fold, and weighted fraction 50/80/95%, fit one
common orientation on the other four folds over the declared 5-degree
yaw/tilt-azimuth and 1-degree tilt grid with maximum tilt 15 degrees. Evaluate
the selected orientation without refitting on the held NORAD fold. Report
candidate count, track count, duration, fitted quantile, and held quantile.

Compare actual receiver labels with 20 deterministic whole-track label
permutations. Permute within scan and RF-lane strata, preserving receiver
counts in every stratum; report unchanged singleton/one-receiver strata and
the number of labels that actually move. Use identical NORAD folds and
permutation seeds at all locations. Both provisional receiver mappings remain.

This is angular concentration generalization, not an RF gain or visibility
likelihood. Use no truth, VAL/TEST, geographic optimization, candidate
reselection, new RF, or position fit. Record all failures explicitly.
