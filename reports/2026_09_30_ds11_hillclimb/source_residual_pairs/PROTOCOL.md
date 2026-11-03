# Conditional same-source residual comparison

Use the already selected target tracks in scans0 and16, original training rows
and the frozen original IID endpoint. Compare cached GLRT and long-pilot-with-
fallback measurements at that same endpoint. No additional position fits,
waveform estimation, orbit updates, held observations or geographic scoring.

For each pair of target tracks, match mutual nearest training timestamps with
absolute separation at most0.25seconds. Break timestamp-distance ties by lower
observation index. Keep a matched observation at most once per pair. Report
every pair including inadequate overlap. Require at least six matches for
descriptive correlation/dispersion summaries; do not enlarge the time window.
Report receiver/RF differences and matched time offsets explicitly.

Use each target's already selected conditional NORAD, with verified candidate
identity ordering. Profile its constant CFO using all of that track's training
observations under the unchanged IID likelihood, then evaluate paired residuals.
Report Pearson correlation, median-centered individual RMS, and common/difference
component RMS after separately centering the two paired sequences. Also report
median-centered paired frequency difference and the corresponding model
prediction difference. Retain raw pair values for inspection.

Common residual structure is not proof of orbit error: receiver-position error,
shared clocks, association mistakes and extraction artifacts can contribute.
Different frequencies and receivers are conditional evidence, not independent
truth. Near-time samples are not simultaneous; quantify their offset rather
than treating them as exact repetitions. This is a diagnostic, not a rule for
discarding tracks or adding nuisance parameters.
