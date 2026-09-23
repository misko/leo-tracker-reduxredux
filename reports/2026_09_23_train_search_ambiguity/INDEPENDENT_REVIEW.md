# Independent review

Reviewed `audit.py` (SHA-256
`88fb8e4c793242e95bb7ae2e0e540d21a7cbb417f4ed33ee2627fc78252710f8`), the
sealed result (SHA-256
`67b9f1649dce79918c7cf069019361961a59d118690b1d0ae49d91c49133979e`),
protocol, README, and `tests/tools/test_train_search_ambiguity.py`. The two
focused tests and Ruff pass.

The beam reconstruction is source-derived and correct. For each actual search
level it uses the previously retained beam plus only trace rows first evaluated
at that level, then applies the same objective/east/north sort and level
spacing as `search_prior`. The result binds all three saved search inputs and
the tool. It correctly reports actual new-evaluation counts: the original
first-group one-scan control has zero 0.78125/0.390625/0.1953125-km
evaluations, while later searches add 18 cells at each of those fine levels.
Its selected-point origin level is therefore the appropriate resolution limit,
not an assertion that every run received the later fine grid.

One publication defect was found: `replay()` deliberately carries a beam
forward through requested-but-unexecuted fine levels with zero new evaluations,
but `plot.py` plots those carried-forward first-group one-scan points as fine
grid gaps. The README text is careful about this distinction; the plot should
filter zero-evaluation levels or explicitly mark them unevaluated before
publication. A regression test should cover that behavior.

The protocol calls for Jaccard identity agreement, while the result supplies
the fraction of common track keys assigned the same candidate. That is a
reasonable and more directly interpretable matched-track measure, and README
labels it correctly; rename the protocol metric or add an actual Jaccard value
to avoid a terminology mismatch. The report's limits on pruning, correlated
prior agreement, and non-calibrated objective gaps are scientifically sound.
