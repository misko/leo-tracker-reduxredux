# Residual curvature transfers across receivers beyond a fitted line

Same-candidate curvature from the opposite receiver improves held residual
prediction in all nine panels, after each target's own training-fitted line
has already been removed. This is a distinct positive result beyond the
earlier slope-transfer experiment. It supports an information-retention audit
of a curvature correction, not immediate promotion into the position model.

| Dataset | Supported / eligible tracks | Improved held predictions | Median paired gain, Hz |
|---|---:|---:|---:|
| DS7 | 597 / 1,281 | 368 / 597 | +4.49 |
| DS8 | 581 / 1,232 | 363 / 581 | +3.94 |
| DS9 | 554 / 1,256 | 379 / 554 | +12.75 |
| Total | 1,732 / 3,769 | 1,110 / 1,732 | +6.27 |

Positive gain means a reduction in per-track median absolute held residual
relative to the target's own training-only linear fit. Units are canonical
11.2-GHz Hz, not metres. Supported tracks span all 72 source scans. The
all-eligible-population median gain is zero because 2,037 targets retain the
unchanged linear fallback; mean gain is +17.55 Hz. Unsupported predictions are
not counted as improvements.

## Matched control

On the 230 targets with both same-candidate and other-candidate opposite-RX
support, same-candidate curvature beats the other-candidate predictor on
189/230 tracks. The controls use exactly the same target population.

| Dataset | Matched targets | Same-candidate median gain, Hz | Other-candidate median gain, Hz |
|---|---:|---:|---:|
| DS7 | 84 | +6.69 | −16.93 |
| DS8 | 76 | +5.95 | −10.69 |
| DS9 | 70 | +12.52 | −10.85 |
| Total | 230 | +7.19 | −12.00 |

Same-candidate prediction improves 164/230 matched targets versus the linear
baseline, compared with 70/230 for other candidates. The target's own quadratic
fit improves 172/230, with median gain +12.10 Hz. On all supported targets, the
own-quadratic gain is +10.64 Hz and improves 1,273/1,732. It is a flexible
training comparator, not an independent calibration.

| Eight-scan panel | Same-candidate median paired gain, Hz |
|---|---:|
| DS7 early | +2.02 |
| DS7 middle | +11.97 |
| DS7 late | +3.58 |
| DS8 early | +5.92 |
| DS8 middle | +2.07 |
| DS8 late | +3.77 |
| DS9 early | +4.55 |
| DS9 middle | +18.35 |
| DS9 late | +17.40 |

## Frozen design

We used the nine existing residual exports, rather than selecting the twenty
largest losing tracks from the recent diagnostic. Of 3,983 inherited eligible
exports, 214 lacked the frozen curvature-test support requirements: 65 DS7,
79 DS8, 70 DS9. This leaves 3,769 targets. All exclusions are recorded.

The target baseline is an intercept and slope fit only to its training samples.
Time is centered and scaled using that target's training mean and span. The
quadratic basis is orthogonalized against the intercept and line on those
training samples. A donor-derived quadratic coefficient multiplies this basis;
therefore adding the correction does not change the target training linear
normal equations. This is a deliberate distinction from a free slope term.

Donors must have the same scan and exact RF, opposite receiver, and at least
50% overlap with the target training span. Their fit uses only donor training
samples inside that span, with at least eight points, at least ten seconds,
and a rank-three quadratic design. Donor intercepts and slopes are fitted but
not transferred. Same-candidate coefficients are combined by median; the
other-candidate control takes medians within candidate, then across candidates.
No held residual influences eligibility, donor selection or fitting.

The [protocol](PROTOCOL.md) and [input manifest](manifest.json) precede scoring.
The [results](results.json) retain all targets, donor identities, coefficients,
held errors and exclusions. The [summary](summary.json) contains all-population,
supported and matched comparisons for each dataset and panel. On a supported
population, the other-candidate summary includes fallback for unsupported
controls; use the matched table for a direct comparison.

## Implication and limits

The result is consistent with candidate-specific nonlinear residual structure
that transfers across receivers. It does not identify its cause: receiver
position, orbit, timing, transmitter behavior and shared extraction errors
remain possible explanations. Residuals inherit fitted location, timing and
training-model candidate assignments from the earlier conditional-bank model.
Thus these transfers are not independent orbit calibration.

The next useful test is to quantify position information lost when this
orthogonalized curvature direction is profiled out, including shared timing
nuisance terms. Preserving the training linear projection does not guarantee
preservation of all geographic information. Only if the information loss is
acceptable should a constrained shared-curvature model proceed to whole-scan
or whole-receiver validation and paired geographic evaluation. Earlier
shared-slope models improved prediction without consistent location gains.

These are interleaved held samples, not causal forecasts. Directed transfers
include reciprocal pairs and are not independent trials. Candidate identities
are conditional model assignments; the geographic reference is inherited and
unsurveyed. No new location was estimated, and no sub-km improvement is claimed.

## Verification

Four tests cover exact quadratic recovery with different receiver linear
terms, held-value mutation isolation, receiver/RF/candidate separation, and
preservation of target training intercept/slope. Ruff passed. Input/source
hashes match the prior slope-transfer evidence. Unique target keys and exact
fallback identity were checked. The numerical run exited zero in 1.23 seconds
under a 120-second cap. No RF collection, production code or QNAP mutation.

```bash
OPENBLAS_NUM_THREADS=1 .venv/bin/python -m unittest discover -s reports/2026_09_29_curvature_transfer -v
OPENBLAS_NUM_THREADS=1 .venv/bin/python reports/2026_09_29_curvature_transfer/study.py prepare
OPENBLAS_NUM_THREADS=1 timeout 120 .venv/bin/python reports/2026_09_29_curvature_transfer/study.py run
```

Outputs use exclusive creation; reproduce in a fresh archived-run context,
not by overwriting the completed artifacts. This report is local research.
