# Free candidate slopes absorb most conditional position information

**Do not treat the preceding cross-RX residual gain as an independently measured
orbit correction.** Allowing one free slope per scan/candidate/exact-RF group
retains only **1.82–23.71%** of the original position information in the most
affected direction across the nine panels. Even the less affected direction
retains only 11.65–34.53%. This is a local conditional design diagnostic, not a
geographic fit or an accuracy/uncertainty estimate.

| Eight-scan panel | Cases | Shared slope groups | Shared slopes: weaker retention | Shared slopes: stronger retention | Per-track slopes: weaker retention |
|---|---:|---:|---:|---:|---:|
| DS7 early | 214 | 109 | 9.58% | 17.46% | 5.67% |
| DS7 middle | 201 | 104 | 12.01% | 28.06% | 10.59% |
| DS7 late | 220 | 110 | 23.71% | 34.53% | 20.94% |
| DS8 early | 223 | 109 | 15.15% | 29.42% | 13.27% |
| DS8 middle | 202 | 99 | 1.82% | 14.40% | 1.34% |
| DS8 late | 192 | 101 | 7.13% | 12.19% | 6.53% |
| DS9 early | 199 | 100 | 4.45% | 15.74% | 3.90% |
| DS9 middle | 207 | 103 | 11.79% | 25.77% | 10.74% |
| DS9 late | 189 | 93 | 2.05% | 11.65% | 1.73% |

Retention is the pair of generalized eigenvalues comparing position information
with slopes free versus slopes fixed to zero, after profiling recording times in
both. It is not a ratio of geographic errors or a calibrated confidence bound.
Both arms use exactly the same previously supported cases. This is **not** the
information loss for the entire 4,328-track localization objective: unsupported
tracks and uncertain candidate components are outside this diagnostic.

## Why the previous positive result is insufficient

[Candidate-specific cross-RX transfer](../2026_09_29_candidate_rx_transfer/README.md)
improved held residual prediction on 1,171/1,847 supported target cases, whereas
other-candidate clock corrections did not transfer reliably. That established
shared conditional residual structure. However, the two receivers share fitted
position and recording time: a wrong location itself produces shared residuals
for the same candidate. Fitting away that structure can remove the location
signal. This experiment quantifies that risk for free linear residual slopes.

It does not prove that orbit errors caused the residuals or that all physically
constrained orbit corrections would fail. A correction measured independently
could remove bias without introducing these unconstrained nuisance directions.
The tested free-slope model is also different from freezing a donor-derived
correction and ignoring its dependence on the fitted location; such freezing
would not make the donor estimate independent evidence.

## Method and checks

The [protocol](PROTOCOL.md) was frozen before execution. Reuse all 1,847 supported
cases from the cross-RX transfer report, in all nine panels. Differentiate each
selected candidate's Doppler prediction at the inherited fitted location and
recording time using existing numerical position/velocity banks. Coordinates
are east/north kilometres and recording-time seconds. Remove a separate constant
from each track by centering its training derivative columns.

Weight by frozen candidate probability times signal responsibility and the
common Student-t4 expected location precision `5/(7*100^2)`. This is optimistic
complete-data linearized information: it omits association uncertainty and its
derivatives, non-Gaussian residual effects, cross-track correlations and model
misspecification. It is not the observed full-mixture Hessian.

The baseline design has two shared position coordinates and eight recording-time
coordinates. A slope column is training-centered time. Analytically profile
either one slope per scan/candidate/exact-RF group or a separate slope per track,
then profile the recording times using a relative-eigenvalue 1e-10 pseudoinverse.
Most groups contain both RXs in the selected subset: respectively 96/109, 95/104,
96/110, 100/109, 90/99, 86/101, 89/100, 96/103 and 88/93 in table order. Remaining
groups have only one RX represented in this subset because transfer support is
directional; their slope is still profiled and they are not silently excluded.

Central differences use 0.001 km and 0.0001 s, then half those values. Maximum
absolute change of a retained-information eigenvalue is below 7e-10 across all
panels. The result therefore is not a finite-difference step artifact at these
points. Timing-grid distances and both-step matrices are retained in results.
Every baseline and augmented timing block has full rank eight.

Two synthetic tests pass: analytic profiling agrees with a direct expanded
design, and a slope-aligned position direction loses all information as expected.
All selected case predictions reproduce the exported residuals to within 1e-7 Hz;
training masks and times match exactly or within 1e-12 s. Every observation,
manifest and numerical-bank artifact is checked against its declared SHA-256.
`results.json` binds inputs, source and protocol and retains all matrices, ranks,
step comparisons and per-panel counts. Ruff lint and formatting pass.

```bash
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python -m unittest discover -s reports/2026_09_29_candidate_information -p 'test_*.py'
OPENBLAS_NUM_THREADS=1 timeout 120 uv run --no-project --with numpy --with scipy python reports/2026_09_29_candidate_information/information.py
```

Execution used one numerical thread and loaded one recording bank at a time,
completing within the 120-second cap. No new propagation, RF, production edit,
parameter optimization or geographic refit occurred.

## Next decision

Keep candidate-specific slopes as a diagnostic, not a default localization
correction. Prioritize an independent orbit/identity constraint, or a constrained
orbit-error model whose information loss is quantified before fitting position.
Any such model must demonstrate held predictive and geographic gains on all
declared panels; better residuals alone remain insufficient. Reliable short-window
sub-km accuracy is still unresolved.
