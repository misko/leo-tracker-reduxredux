# Calibration background prerequisite audit

The proposed defensible reference population is empty. Across 1,356 calibration reception
windows in the pilot dataset, zero windows have every nominated track-candidate prediction
marked invisible. The confirmation dataset contributes zero calibration windows because its
four records are evaluation-only. Thus the observed negative fraction is 0/1,356 = 0.

There are no receiver candidate-count observations in this population, so its RX0/RX1 means,
variances, and empty fractions are undefined. All 12 calibration lanes contain zero qualifying
negative windows: the across-lane mean and population variance are both zero. Likewise, the
fixed 16-bin canonical-frequency-circle counts are all zero, and a uniformity statistic is
undefined rather than evidence of uniformity.

This rules out learning a reference frequency or count background from calibration windows
where the nominated hypotheses are all geometrically invisible. Widening the definition after
seeing this absence would change the reference population. A subsequent model must instead
declare an unconditional empirical background estimated from calibration reception data, or
use another predeclared external reference. Such observations are not labelled clutter truth:
visible nominated hypotheses may be wrong, omitted emitters may be present, and raw candidates
have no common-emitter labels. The appropriate claim is an empirical background distribution,
not a learned physical clutter process.

The machine receipt is [background-audit.json](background-audit.json). The frozen command,
code/test hashes, and input hashes are in
[background-audit-launch.json](background-audit-launch.json). The audit read existing dataset
JSON only, used one thread, completed below the 30-second bound, and fit no parameters.

## Unconditional observational reference

A separate frozen audit describes all 1,356 calibration reception windows. RX0 has mean
candidate count 2.2441 and population variance 3.1417; RX1 has mean 1.5516 and variance
2.9582. Variance-to-mean ratios are 1.4000 and 1.9066, respectively. Empty fractions are
0.2795 for RX0 and 0.4270 for RX1, compared with Poisson values 0.1060 and 0.2119 at the
observed means. Both receivers are empty in 0.2633 of windows, and at least one is empty in
0.4432. These discrepancies show that a constant-rate Poisson count model is inadequate as
a literal description of the mixed calibration observations.

The 12 lane window counts range from 100 to 129 (mean 113, population variance 67.5). Across
5,147 candidates, the fixed canonical-circle bin counts are
`274, 309, 320, 319, 341, 382, 367, 364, 248, 320, 280, 330, 280, 297, 324, 392`;
the Pearson descriptive statistic against equal bins is 77.204. This is descriptive
nonuniformity, without an independence-based p-value because candidates share windows,
receivers, lanes, and recordings.

This full population mixes possible nominated signals, omitted emitters, and background.
It can support an unconditional empirical reference with lane/receiver heterogeneity, but
it is not negative truth and cannot identify a physical clutter process. Its separate receipt
is [unconditional-background-audit.json](unconditional-background-audit.json), with frozen
hashes in
[unconditional-background-audit-launch.json](unconditional-background-audit-launch.json).
The original strict audit output and launch receipt remain unchanged; its source is preserved
as `strict-background-audit-source.py`.
