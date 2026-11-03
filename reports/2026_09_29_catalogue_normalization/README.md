# Full-catalogue normalization: score margins change, location winners do not

The bounded prototype evaluated every bank-eligible track in one frozen
outside-pool scan from each of DS7, DS8 and DS9. Exact full-catalogue scoring
preserves the best satellite candidate at all 2,715 track/location/time
settings and the winning location in all 18 scan-level comparisons. It changes
relative location scores, but this experiment does not demonstrate improved
geographic accuracy.

| Dataset | Tracks | Settings | Minimum training signal mass retained | Minimum complete-track signal mass retained | Changed location winners |
|---|---:|---:|---:|---:|---:|
| DS7 | 59 | 885 | 99.999878% | 99.99999996% | 0 / 6 |
| DS8 | 58 | 870 | 99.936456% | 99.999170% | 0 / 6 |
| DS9 | 64 | 960 | 99.997413% | 99.999981% | 0 / 6 |

Settings are repeated evaluations of 181 tracks, not 2,715 independent trials.
The six comparisons per dataset are training and complete-track scores at
each of three timing offsets. Complete-track scores include training points;
they are not an independent held-out partition.

## What the prototype separates

All expressions use the same 0.8 signal / 0.2 background prior and contrast
likelihood. The original expression divides the retained-candidate likelihood
sum by the retained-visible count. The exact alternative divides the entire
visible-catalogue likelihood sum by the full-visible count. An intermediate
expression uses only the retained numerator with the full denominator.

That intermediate expression is a pointwise lower bound on the exact density,
not an independently normalized model. Its maximum scan-level log-score gap
from exact full scoring is 0.000340 in these settings. By comparison, changing
the normalization changes a location's score relative to the configured
center by as much as 7.793290 log units. The denominator effect therefore
dominates omitted numerator mass on this particular panel.

These are model-definition differences, not evidence that either model's
signal probability is calibrated. A lower absolute likelihood after changing
the candidate prior is not itself worse prediction or better calibration.
See the [full comparison table](TABLE.md) and [machine-readable summary](summary.json)
for location winners and separate numerator effects. Detailed relative scores
for all five locations are preserved in the summary.

## Frozen design and verification

The [protocol](PROTOCOL.md) selects the earliest previously frozen outside-pool
target in each dataset: DS7_0, DS8_0 and DS9_0. Locations are the configured
center, the existing 24-scan fitted location and three existing 8-scan fitted
locations. Timing offsets are fixed at −5, 0 and +5 seconds. No location or
timing fit, timing integration, target-based tuning or new RF collection occurs.

Causal catalogue snapshots are reconstructed through read-only archive ports,
verified by digest and propagated at the actual observation epochs. The
original training-mask visibility convention applies to both score partitions.
All retained predictions replay exactly (0 Hz difference), and all retained
visibility masks match. All 45 complete-scan scalar replay checks pass; the
maximum log-score discrepancy is 9.10e−12. Manifest/source bindings, complete
track coverage, comparison counts and effect signs pass the summary checks.
All three workers exit zero within their 180-second caps: 158.03, 118.16 and
168.41 seconds. Ruff passes.

The pinned deployed interpreter is used as a research numerical oracle;
runtime source digests are recorded in each dataset output. This adds no
production dependency. No production code, scientific fixtures or QNAP paths
are changed. Outputs are local and have not been published by this experiment.

## Decision and next test

Do not promote a new location model from this result. The existing shortlists
capture nearly all candidate likelihood mass at these selected local points,
and exact normalization has not changed their winners. This narrows the
hypothesis: local omitted candidates are unlikely to explain these particular
score comparisons, while signal/background prior normalization remains an
explicit modeling choice.

A next bounded experiment can compare source-only fits under the two candidate
priors, then score frozen outside scans with one shared timing offset integrated
per scan. Any retained-numerator acceleration must keep its approximation label
and audit omitted mass at the resulting fitted locations. Broader continuous
search cannot inherit completeness from this finite grid; the preceding
[domain probe](../2026_09_29_catalogue_domain/README.md) found missing leading
candidates at 100 km offsets. Full-catalogue equal-visible priors also require
physical justification before interpreting them as calibrated confidence.

One scan per dataset, site-conditioned input banks and an exposed, unsurveyed
geographic reference cannot establish blind sub-km accuracy. This report is
an exact scoring audit, not a new single-scan or multi-scan error result.

Reproduction uses `study.py prepare`, `study.py batch`, then `summarize.py` in
this directory. Numerical outputs use exclusive creation; preserve this run
and use a fresh archived-run context when reproducing it.
