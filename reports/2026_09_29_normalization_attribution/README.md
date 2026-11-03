# Catalogue normalization mainly changes background weighting

An exact decomposition of the preceding full-catalogue experiment shows why
relative location scores change despite essentially complete local candidate
coverage. The largest contribution is the interaction with the background
mixture, rather than changes in visible-candidate counts between locations or
omitted candidate likelihood mass.

Across 72 comparisons of a fitted location against the configured center:

| Contribution to relative log-score change | Maximum absolute value |
|---|---:|
| Visible-candidate count ratio | 0.0186045 |
| Omitted signal numerator mass | 0.0000247 |
| Background-mixture interaction | 7.8011158 |
| Total change | 7.7932896 |

These are separate maxima and need not occur in the same comparison; do not
add the table rows. The total is the exact full-catalogue score contrast minus
the retained-catalogue score contrast. Positive values mean the alternative
location gains relative to center. They are not geographic errors.

## Existing 24-scan location versus center, at fixed timing zero

| Dataset | Score partition | Count term | Omitted numerator | Background term | Total change | Top five tracks' share of gross change |
|---|---|---:|---:|---:|---:|---:|
| DS7 | Training | +0.005975 | <0.000001 | −0.052300 | −0.046325 | 99.3% |
| DS7 | Complete track | +0.005975 | 0 | −0.001893 | +0.004082 | 99.5% |
| DS8 | Training | −0.001800 | +0.000002 | +0.210262 | +0.208464 | 96.8% |
| DS8 | Complete track | −0.001800 | +0.000001 | +0.159609 | +0.157810 | 97.2% |
| DS9 | Training | +0.003914 | <0.000001 | −0.006046 | −0.002132 | 91.9% |
| DS9 | Complete track | +0.003914 | 0 | +0.452271 | +0.456185 | 90.9% |

Concentration uses the sum of absolute per-track contributions, avoiding an
unstable percentage of a nearly cancelling signed total. Track selection for
this attribution is descriptive and retrospective, not a new exclusion rule.
Training and complete-track partitions overlap. These target scans were not
used to fit the existing locations, but timing is fixed here, not integrated.

## Exact identity

Let R and V be retained-visible and full-visible candidate counts, m the
retained fraction of the full signal numerator, and p_R and p_V the signal
responsibilities under the two mixtures. With the same signal/background prior:

```
log L_full_mixture − log L_retained_mixture
  = log(R/V) − log(m) + log(p_R) − log(p_V).
```

We compute this identity per track at each location, then subtract that
track's corresponding center identity and sum across the scan. The three
terms are count normalization, omitted numerator, and background interaction.
The last term is an algebraic attribution, not an independently randomized
causal intervention. Changing normalization changes responsibilities; these
effects cannot be interpreted as separate physical mechanisms.

The [analysis script](analyze.py) verifies the preceding experiment's evidence
seal and checks every evaluated identity. Maximum error is 1.07e−13 log units.
An independent constructed-density test covers 15 combinations of signal
strength and omitted mass, including nearly pure signal and background.
The test and Ruff pass. [Full results](result.json) preserve every track's
contribution and responsibilities, with the source seal digest.

## Implication for sub-km development

Increasing local candidate support alone is not supported as the next accuracy
fix by this panel. The useful fitting comparison is how the two explicitly
defined candidate priors weight ambiguous tracks against the same background.
Keep all tracks, fit only on source scans, and compare excluded-scan predictions
with shared per-scan timing integrated. Exact full-catalogue audits must cover
the resulting fitted positions; this finite point grid cannot certify an
approximation throughout optimization.

Do not tune the background fraction or remove the retrospectively influential
tracks using these target results. The full-visible uniform prior itself is
not established as physically calibrated. No new fit, geographic error result,
or sub-km validation is claimed. The [source experiment](../2026_09_29_catalogue_normalization/README.md)
retains unchanged location winners in all 18 comparisons and covers only one
scan per dataset. Reference and site-conditioning limitations remain.

This diagnostic reuses existing evidence, collects no RF and changes no
production code. Artifacts are local. Reproduce with `python3 analyze.py` in
a fresh output context and `python3 -m unittest discover -s . -p 'test_*.py'`.
