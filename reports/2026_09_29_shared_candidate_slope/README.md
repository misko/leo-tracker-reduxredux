# Joint marginal candidate-slope prototype

Tests whether tracks assigned to one candidate in one recording should share
a small residual Doppler slope. This follows the candidate-group influence
diagnostic, without discarding tracks or fitting an unconstrained slope to each
track. Research-only implementation; no new radio collection or production edits.

**Decision: do not promote this model for localization.** Both widths improve
held prediction on all nine panels, but neither consistently improves geographic
accuracy. This is a concrete example of better residual prediction failing to
produce a better position estimate.

## Results

Median geographic error across the three eight-scan panels per dataset:

| Dataset | Baseline, m | Shared slope SD0.5 Hz/s, m | SD2 Hz/s, m |
|---|---:|---:|---:|
| DS7 | 2,023.56 | 2,102.61 | 2,655.94 |
| DS8 | 1,721.07 | 1,921.95 | 1,736.79 |
| DS9 | 876.13 | 836.66 | 1,457.06 |

At SD0.5, geographic error improves in2/9 panels and sub-km coverage remains
2/9. At SD2, error improves in4/9 but sub-km coverage falls to1/9. All six DS7
comparisons worsen geographic accuracy. The stronger model improves every
panel's joint held score, yet at its new position the original model's held
score worsens in9/9; at SD0.5 it worsens in8/9. This separates improved latent
residual prediction from evidence for improved geographic estimation.

All18 fits qualify, including optimizer success, no boundary, physical gradient,
finite-difference derivative audit, and128-versus256-node integration audit.
The largest integration discrepancy is0.002336 held-log-score units, below the
fixed0.01 threshold. Every process exits zero within120seconds, and all final
input/source hashes verify. Two synthetic test methods and Ruff checks pass.

The conservative shared prior did not avoid the location-confounding concern
identified by the earlier free-slope information analysis. These outcomes do
not show that a physical shared Doppler error is absent; they show that this
conditional grouping and latent correction cannot identify a consistently
better location from the current data. Do not increase the prior width based
on these geographic errors. Keep the q020 baseline and prioritize independent
timing/orbit/identity constraints or validation that withholds whole groups,
rather than further improving interleaved residual scores alone.

## Probability model

Training-baseline assignments define recording/candidate groups when the MAP
candidate's joint signal probability is >=0.5. Groups with at least two tracks
share a canonical-Hz/s residual slope s. Its prior is a zero-mean Gaussian,
truncated and renormalized at +/-6 sigma, with fixed sigma0.5 or2 Hz/s. This
is explicitly a truncated model; the approximately2e-9 excluded prior mass is
not a bound on possible posterior truncation effects.

For each grouped track, only its designated candidate component receives the
additional slope. All alternative candidates, the 20% unassociated-trend
background, and ungrouped tracks retain the original model. A per-track
constant is still eliminated through the original Student-t4 contrasts.

For a group G, the likelihood is:

    L_G(x) = integral p(s) product_(j in G) L_j(x, s) ds.

This integrates the product; multiplying independently integrated tracks
would not represent shared error. Analytic parameter gradients average the
sum of conditional track gradients under the group's slope posterior.
E/N and all eight recording times are jointly optimized. Candidate mixture
weights remain variable throughout. There are no optimized slope parameters.

Held prediction uses the full-data group integral minus the training-data
group integral in log space, evaluated at training-fitted position and timing.
The full-data integral updates latent-slope uncertainty as part of joint
predictive scoring; it does not refit position or train on held observations.
Groups themselves are selected using training evidence, so comparisons are
exploratory conditional-model results rather than untouched-group validation.

## Validation and artifacts

[Protocol](PROTOCOL.md) fixes widths and gates before geographic outcomes.
[Full table](TABLE.md) reports every arm; `summary.json` includes full numerical
results. Per-run JSON files retain group memberships, optimizer status,
derivative and quadrature audits, geographic coordinates, both held scores,
elapsed time, and verified input/source hashes. Process receipts retain exits.

Tests cover shared integration versus independent integration, normalized
quadrature, analytic derivatives, exact zero-slope recovery of baseline score,
gradient and held score, and held-value isolation. Numerical integration uses
128 nodes and is audited at256; finite-difference checks audit fitted gradients.

The common-model held comparison evaluates the original baseline likelihood
at the new geographic and timing estimate. It helps distinguish better latent
residual prediction from a better position under the original objective, but
is not independent physical truth. Geographic errors use the inherited exposed,
unsurveyed reference at one site. Candidate numbers are not verified identities.
One local start per arm does not demonstrate global optimality. No robust
short-window sub-km claim can follow from these results alone.

```bash
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python -m unittest discover -s reports/2026_09_29_shared_candidate_slope -p 'test_*.py'
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python reports/2026_09_29_shared_candidate_slope/batch.py
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy python reports/2026_09_29_shared_candidate_slope/summarize.py
```
