# Full-visible prior-mass approximation: retain the baseline

The bounded source-only fitting prototype passes numerical checks, but does
not improve accuracy consistently. DS8 improves slightly; DS7 and DS9 worsen.
Across 12 excluded target scans the fitted locations lose 9.6451 predictive
log-score units under the common original q020 evaluation model. Do not
promote this approximation as an accuracy improvement.

| Dataset | Source scans / tracks | Baseline reference error | New reference error | Location shift | Excluded-scan score change | Target wins |
|---|---:|---:|---:|---:|---:|---:|
| DS7 | 4 / 239 | 2,855.8 m | 2,940.7 m | 85.0 m | −6.1699 | 1/4 |
| DS8 | 4 / 255 | 530.2 m | 521.3 m | 11.3 m | +2.9151 | 4/4 |
| DS9 | 4 / 248 | 2,196.1 m | 2,264.2 m | 75.2 m | −6.3902 | 0/4 |

Errors use the inherited exposed, unsurveyed reference. They are not blind
validation of absolute accuracy. Each row is one four-scan location fit,
not a median across independent sets. Sub-km source fits remain 1/3.

## What was tested

Use the first four scans of each previously defined early-eight DS7/DS8/DS9
panel for fitting and the remaining four for prediction. Reuse the qualified
original source fit as a single warm start, verify its likelihood replay and
preserve the same source/target partition. No reference or target scores enter
optimization or select hyperparameters.

For each source track, reconstruct the full causal catalogue through read-only
archive ports and count visible candidates at the original source fit and its
fitted scan timing. Freeze this count V0. Optimize:

```
0.8 × sum(retained-visible candidate densities) / V0
  + 0.2 × original background density.
```

This retains the full-visible prior mass approximately, rather than normalizing
over the much smaller retained-visible candidate set. It is an unnormalized
optimization surrogate, not a new normalized probabilistic model. Because
the exact visible count can vary with location and timing, it is not guaranteed
to be a lower bound on the location-dependent exact full-catalogue expression.

The implementation shifts the background log density inside the existing
mixture and subtracts the common log factor outside it. This gives the stated
expression and preserves its local responsibility-weighted gradient when
visible sets are unchanged. The background is restored after every call.
A direct constructed-density test checks training and complete-track scores,
per-track score consistency, finite-difference gradients and state restoration.

## Exact full-catalogue source audit

Reconstruct and propagate the full causal catalogue independently at both the
old and resulting source fits. Compute the full numerator and actual visible
count rather than using the optimization approximation.

| Dataset | Surrogate source gain | Exact source gain | Final exact minus surrogate | Tracks with changed visible count | Minimum final retained signal mass | Missing best candidate |
|---|---:|---:|---:|---:|---:|---:|
| DS7 | +0.223373 | +0.229299 | +0.007139 | 8/239 | 99.613641% | 0 |
| DS8 | +0.013137 | +0.014742 | +0.001357 | 1/255 | 99.999999% | 0 |
| DS9 | +0.156155 | +0.146038 | −0.021344 | 5/248 | 99.999433% | 0 |

Visible counts change by at most one candidate per track between the two
points. All three optimization improvements survive the exact source audit,
but their target consequences are mixed. Exact-minus-surrogate differences
combine omitted numerator mass, frozen-count error and fresh propagation
versus interpolated retained-bank predictions. These audits do not separately
identify those effects or certify the approximation along the optimization
path. No claim of exact full-catalogue optimization is made.

## Excluded-scan evaluation and validation

Evaluate both locations with the same original q020 retained-bank model on
every target scan. Integrate one shared timing offset per scan across −5 to
+5 seconds; do not maximize timing separately or integrate it independently
per track. This common scoring rule tests the transferred location change,
not whether the alternative candidate prior is itself a calibrated predictive
distribution.

All three fits are qualified by the pre-existing optimizer, boundary and
gradient gates. Maximum gradient-audit error is 1.33e−6; maximum absolute
optimizer gradient is 0.000278. All 24 target integrals pass the 16/32-order
quadrature comparison, maximum difference 0.000216 log units. None needs
refinement. Maximum scalar replay discrepancy is 1.82e−11. All workers exit
zero in 190–201 seconds, within their 300-second caps. Ruff and the model test
pass. Frozen source hashes and recorded deployed oracle module hashes verify.

## Decision

Keep the original baseline. This first three-panel test provides no consistent
accuracy benefit from changing local signal-prior normalization alone. The
effects are small and disagree across datasets, despite small exact source
likelihood improvements. Do not select DS8 or tune priors to these targets.

The normalization audit remains valuable for interpreting confidence, but
this result lowers its priority as an immediate sub-km accuracy method.
Further work should prioritize independently transferable measurement or
timing information; more fits on this exposed target panel would not establish
generalization. Site-conditioned candidate banks and the lack of surveyed
reference and independent UTC calibration remain limitations.

See [protocol](PROTOCOL.md), [summary](summary.json), [model](surrogate.py),
[runner](run.py) and per-dataset raw results and process receipts. Numerical
work uses the pinned deployed interpreter only as a read-only research oracle.
No new RF, production changes or QNAP writes occur. Artifacts are local.

Reproduce in a fresh output context:

```bash
python3 reports/2026_09_29_normalization_fit/batch.py prepare
python3 reports/2026_09_29_normalization_fit/batch.py run
python3 reports/2026_09_29_normalization_fit/summarize.py
```

Outputs use exclusive creation to preserve this run's evidence.
