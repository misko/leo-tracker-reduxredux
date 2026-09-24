# DS1 reference-free joint group weighting diagnostic

## Result

The sealed iteration-8 to iteration-10 artifacts support replacing arbitrary
equal group weights with a **source-tempered, curvature-and-scale-normalized
score**.  It uses only sealed training inference: the group-specific local
proposal surfaces, hard associations, and already-audited exact losses.  It
does not read any post-seal evaluation artifact or geographic reference.

For DS1, the resulting weights are `0.2742` for `20260921_00` and `0.7258`
for `20260921_16`.  The difference is driven mainly by the 16 group's steeper
two-dimensional local position curvature, with a smaller contribution from
candidate/session coverage.  This is an analytical rerank of iteration-10's
eight existing exact finalists, not a new coordinate search or an orbit fit.

The proposed score retains the equal-group winner:
`(37.858228335, -122.478962459)` degrees.  That coordinate is independently
the best existing exact finalist for both groups, so the unchanged winner is
a robustness check rather than evidence that the new weights are validated.

## Why equal weights are not the only reference-free choice

Equal group weighting protects against raw-observation-count dominance, but
it assigns identical authority to groups with different local position
sensitivity and source coverage.  The exact group losses also live on
different baselines, so direct loss averaging mixes fit scale with location
evidence.  A geographic reference is not needed to measure either property:
the sealed, tau-profiled training surface provides them locally.

For a predeclared candidate set `C`, use:

```text
J(x) = sum_g w_g * (L_g(x) - min_{c in C} L_g(c)) / s_g

w_g = sqrt(D_g) * sqrt(det(H_g / s_g))
      / sum_h [sqrt(D_h) * sqrt(det(H_h / s_h))]
```

`L_g(x)` is group `g`'s exact capped loss.  `H_g` is the local 2-by-2 Hessian
of that group's tau-profiled proposal objective in east/north kilometres, and
`s_g` is its predeclared local objective-noise scale.  `D_g` is the geometric
mean of candidate entropy-effective count and distinct-session count, capped
by distinct tracks.  The square root tempers source coverage for dependence
within a session; it deliberately does not turn every track into independent
evidence.

Subtracting `min_C L_g` only fixes each group's zero point and does not affect
the ranking after weights are frozen.  The formula is therefore a normalized
uncertainty/information score, while retaining separate group nuisance fits.

## Evidence from the sealed artifacts

Iteration 8's coarse union winner moved 0.276 km in iteration 9 and then
0.109 km in iteration 10's symmetric local refinements.  The balanced exact
loss fell from `0.05825069` to `0.05812766`; all three records are
reference-free.

| Group | Local Hessian eigenvalues (loss/km²) | Local loss range | Quadratic residual MAD | Median tau gap | Candidate effective / sessions | Source coverage `D` | Weight |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `20260921_00` | 0.000481, 0.000769 | 5.70e-05 | 2.63e-08 | 0.00936 | 80.81 / 6 | 22.02 | 0.2742 |
| `20260921_16` | 0.000954, 0.002336 | 4.61e-05 | 3.82e-08 | 0.00730 | 109.31 / 6 | 25.61 | 0.7258 |

Both fitted Hessians are positive definite.  The 16 group has normalized local
area information of `1492.94 / km²`, versus `608.34 / km²` for the 00 group;
after conservative source tempering their information values are `7555.24`
and `2854.64`, respectively.  Both quadratic residual MADs fall below the
predeclared `1e-6` loss floor.  That floor is used for normalization so a
nearly deterministic re-profiled grid cannot create an unbounded weight.  The
raw MADs and tau gaps remain in the JSON as separate diagnostics rather than
being misrepresented as independent-observation uncertainty.

The sealed winner's hard associations show 476 tracks, 109 NORAD candidates,
and 6 sessions for the 00 group; the 16 group has 298 tracks, 128 candidates,
and 6 sessions.  Raw track totals are reported but excluded from `D` because
they are strongly correlated within a session and candidate.

## Existing exact-finalist rerank

The table is limited to iteration-10's eight already exact-audited finalists.
No new proposal scan or exact orbit comparison was run.

| Proposed rank | Equal rank | Latitude | Longitude | Normalized score |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 1 | 37.858228335 | -122.478962459 | 0.0000 |
| 2 | 2 | 37.858228335 | -122.478406877 | 6.6996 |
| 3 | 6 | 37.858228335 | -122.478406903 | 6.9259 |
| 4 | 3 | 37.858666963 | -122.478962459 | 10.3849 |
| 5 | 4 | 37.858666963 | -122.478962432 | 10.6791 |
| 6 | 5 | 37.858666963 | -122.478962465 | 10.6862 |
| 7 | 7 | 37.858666963 | -122.478406903 | 18.2487 |
| 8 | 8 | 37.858666963 | -122.478406877 | 18.8890 |

The second and third places favor a very small 16-group loss increase over a
larger 00-group increase, consistent with the 16 group's higher local
information.  This ordering is diagnostic only: its weights were derived
after iteration 10 completed, so a future selection must freeze the formula,
scale floor, neighborhood, and source-coverage rule before creating the
candidate lattice.

## Required prospective protocol

1. Before the next local refinement, freeze a symmetric diagnostic lattice
   around the prior sealed winner and fit each group `H_g`, `s_g`, and `D_g`
   from training inference only.
2. Require a positive-definite Hessian and a predeclared residual-quality
   check.  If either fails, use normalized equal weights or a documented floor
   weight; do not tune a fallback with post-seal results.
3. Freeze the weights before scoring the next candidate lattice.  Keep hard
   associations, tau, per-NORAD rates, and per-track CFOs group-specific.
4. Exact-audit a bounded finalist set, select with `J`, then perform the
   post-seal comparison separately.  A holdout by whole session is needed
   before interpreting these weights as calibrated uncertainty.

## Artifacts and reproduction

- `joint-weighting.json` is the machine-readable diagnostic, including hashes
  of every sealed input, group metrics, iteration progression, and all eight
  reranked finalists.
- `analyze.py` performs a read-only analysis of the three inference records.

```bash
.venv/bin/python reports/2026_09_24_ds1_joint_weighting/analyze.py
```
