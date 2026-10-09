# Retain 125 Hz; narrowing the likelihood does not repair region loss

All 148 members completed: DS16 63, DS17 51 and DS18 34, with all 592 raw
fits independently qualified and no fallback or input failure. This is consumed
development data, not independent validation. Both arms fail the predeclared
acceptance criteria. Production B7 remains unchanged.

| Pooled position metric | Fitted c, 125 Hz | Fitted c, 100 Hz | c = 0, 125 Hz | c = 0, 100 Hz |
|---|---:|---:|---:|---:|
| Mean km | 1.317354 | 1.290684 | 1.679102 | 1.665395 |
| Median km | 0.863677 | 0.804999 | 1.115160 | 1.106889 |
| p95 km | 2.269173 | 2.098582 | 3.177642 | 3.046137 |
| Worst km | 53.400741 | 54.835462 | 54.781204 | 56.772570 |

Fitted-c mean improves 2.02% and median 6.79%, but the largest failure worsens
by 1.435 km. In c=0 the mean improves only 0.82%, while the worst error grows
by 1.991 km. The catastrophic member in both arms is DS18-022,
`scan-fw-f1a32cacd910c005`. All starts, banks and fit budgets are matched;
these local fits do not revisit the regional search. The change cannot restore
a region discarded upstream.

The worst case's frequency RMS improves 108.565 to 92.532 Hz fitted-c and
110.395 to 92.451 Hz c=0, while position worsens and nuisance penalties rise.
This is evidence against treating improved in-sample frequency fit as better
localization. Across members, fitted-c has 101 improvements and 47 regressions;
c=0 has 83 improvements and 65 regressions. Each arm adds one regression over
1 km relative to its matched control.

Here 125/100 Hz is the frequency likelihood width. It is separate from the
2-second timing prior and hard ±60 Hz/s receiver-slope constraint. All four
fits use the same archived fitted-derived starting state; c=0 locks the RF
calibration coefficients. Consequently the matched c=0 125 Hz control differs
from the independently archived c=0 endpoint. Both are reported separately.

![Full position comparison](comparison.png)

The next experiment keeps 125 Hz and evaluates generic retained-region recovery
across the full 193-member development scope. The ac11 diagnostic demonstrates
that this can rescue one discarded region, but it does not establish population
accuracy. Reaching the 0.4 km objective will also require reducing ordinary
errors; this experiment's fitted-c median remains 0.805 km.

## Reproducibility and reporting corrections

The numerical protocol was published before fitting and remains unchanged.
All 2,300 frozen hashes were verified. A reporting-only first attempt failed
because five completion documents were bound transitively through frozen
ancestor digests, rather than direct file hashes. The reporting helper now
verifies that original canonical binding; it did not rerun or modify fits.
[The failed attempt](report-attempt-01.json) remains recorded.

A legacy loader checks an archived error field for receipt consistency only;
it does not use that value for model construction, seeds or winners. This
qualifies the frozen README's overly broad no-reference-field wording; see
[the dependency audit](REFERENCE_DEPENDENCY_AUDIT.md).

[Complete results](RESULTS.md), [independent audit](REPORT_AUDIT.md),
[all per-member metrics](summary.json), and [raw archive instructions](RESULT_ARCHIVE.md)
preserve all members, matched arms, failures, frequency effects and provenance.
No RF collection, reserve access, QNAP mutation or production change occurred.
