# Curvature preserves substantially more position information than free slope

On the same 1,732 supported tracks, a free shared orthogonalized curvature
coefficient retains **62.6–86.6%** of local information in the most affected
geographic direction. A free shared slope retains only **1.8–23.9%**. All nine
panels pass the numerical gates. Combined with the preceding cross-receiver
prediction result, this supports a bounded curvature-model prototype, while
leaving actual geographic improvement unproven.

| Dataset | Early | Middle | Late |
|---|---:|---:|---:|
| DS7 shared curvature | 80.30% | 70.88% | 62.56% |
| DS8 shared curvature | 71.95% | 85.33% | 84.49% |
| DS9 shared curvature | 79.94% | 74.13% | 86.57% |
| DS7 shared slope | 9.60% | 12.03% | 23.87% |
| DS8 shared slope | 15.48% | 1.80% | 7.14% |
| DS9 shared slope | 4.43% | 11.76% | 2.04% |

Percentages are minimum generalized information eigenvalues relative to the
same-population baseline, after profiling recording timing. They are not
accuracy percentages, calibrated confidence, or metre-scale error estimates.
The second geographic-direction curvature retention ranges from 73.7–96.4%.

![Position information retention](retention.png)

## What was measured

The preceding [curvature transfer experiment](../2026_09_29_curvature_transfer/README.md)
found improved held residual prediction across all nine panels. This audit
uses exactly its 1,732 supported tracks, at their inherited location, timing
and candidate assignments. It does not select tracks by reference error or
fit new geographic positions.

The local design has east/north sensitivity and one time-offset sensitivity
per scan. Per-track constant frequency is removed. We reuse the earlier
candidate_information weighting (fixed training candidate/signal weights
times 5/70000) and profile nuisance directions by Schur complement. This is
a conditional design proxy, not the observed Hessian of the full mixture.

For the new nuisance direction, centered time squared is projected against
the training intercept and linear time; its residual is the curvature basis.
It preserves the training linear projection. Physical seconds squared are
used so that shared coefficients have common Hz/s² units across tracks.
Coefficients are shared by recording, physical candidate number and exact RF.
The comparison profiles an unrestricted coefficient, without a prior.

We also profile a separate curvature coefficient per track. Minimum retention
is 62.52–86.55%, only slightly below the shared version. Thus most protection
comes from removing the linear component of the nuisance basis, rather than
sharing alone. This does not justify adding arbitrary nuisance directions.
The matching free-slope comparison uses identical tracks, weights and timing
parameters; it must not be compared as if it used all earlier slope-support
tracks, whose population was slightly larger.

See the [complete table](TABLE.md), [results](results.json) containing both
geographic eigenvalues and information matrices, and [protocol](PROTOCOL.md).

## Next implementation and acceptance evidence

Prototype a conservative curvature correction on a frozen source split, then
test whole-receiver or whole-scan prediction as well as paired geographic
errors. Preserve the target-linear protection, physical scaling, alternative
candidate components and background likelihood. Do not choose correction
strength from the exposed geographic reference or target prediction errors.

The remaining 13.4–37.4% information loss in the most affected direction is
material. A prior may reduce that local loss but cannot guarantee better
estimation. The information audit and cross-RX transfer do not establish the
physical cause: location, timing, orbital and measurement errors remain
confounded. The model should be promoted only on actual prediction and
geographic evidence, not this proxy alone. No new sub-km gain is claimed here.

## Numerical checks and provenance

All 72 scans and nine panels completed in 20.10 seconds under a 120-second cap.
Residual replay was exact; source timestamps and masks matched. Finite
differences at 1 m east/north and 0.1 ms timing, versus half those steps,
changed retained-information eigenvalues by at most 8.18e−10. The nearest
timing interpolation knot was 0.11737 ms away, beyond the largest step.
Candidate visibility held at all derivative evaluations. All retentions
lay within [0,1] to the frozen tolerance.

Two new tests cover translation-invariant curvature, training linear
orthogonality, and the fact that curvature can still remove a geographic
direction. Two reused tests verify nuisance profiling against an explicit
joint design and slope confounding. All four passed, as did Ruff.

The initial invocation used the repository environment, which lacks SciPy;
tests and execution stopped at import before numerical work. The successful
run used the isolated NumPy/SciPy environment shown below. No statistical
settings changed. All input/code hashes are in results.json; no production,
RF, QNAP, or golden-fixture changes were made. This is local research using
site-conditioned banks and an inherited, unsurveyed geographic reference.

```bash
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python -m unittest discover -s reports/2026_09_29_curvature_information -v
OPENBLAS_NUM_THREADS=1 timeout 120 uv run --no-project --with numpy --with scipy python reports/2026_09_29_curvature_information/study.py
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy --with matplotlib python reports/2026_09_29_curvature_information/summarize.py
```

The numerical output uses exclusive creation; reproduce in a fresh archived-run
context rather than overwriting the completed result.
