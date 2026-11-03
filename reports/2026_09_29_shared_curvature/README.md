# Shared curvature improves six of nine geographic fits

The conservative shared-curvature prototype improves reference-relative
geographic error in **6/9 panels**, with lower dataset medians on DS7 and DS8.
DS9's median worsens. Sub-km coverage remains **2/9**. All numerical fits pass,
but this is a promising local prototype, not a promoted localization model.

| Dataset | Baseline median error | Curvature median error | Improved panels |
|---|---:|---:|---:|
| DS7 | 2,023.56 m | 1,649.11 m | 2/3 |
| DS8 | 1,721.07 m | 1,489.65 m | 3/3 |
| DS9 | 876.13 m | 949.72 m | 1/3 |

![Paired geographic errors](geographic.png)

The new model's conditional interleaved held score improves on all nine
panels, totaling +4034.118 natural-log units. However, evaluating the original
q020 model at the new fitted coordinates/times gives worse held scores on
8/9 panels, totaling −196.626. The latent curvature term explains substantial
residual structure; that alone does not establish a better location.

The [full panel table](TABLE.md) records paired errors, movement and both
held-score comparisons. Positions move 141–525 m. No reference or held score
selected a prior width, group membership, initialization or successful fit.

## Model and frozen choices

The prior is fixed at **0.1 canonical Hz/s²**, a zero-mean Gaussian explicitly
truncated and normalized at ±6 standard deviations. This was an engineering
choice frozen before evaluation, not an empirically calibrated orbit prior.
Only one width was run. Each panel starts from its existing cached q020 fit,
so these are local warm-start comparisons rather than a new multistart search.

Every track's curvature basis is time squared with its training intercept
and linear time projection removed. The same fixed basis is used for training
and full likelihood; held samples never redefine that projection. Coefficients
use physical seconds-squared scaling and are shared by recording, physical
catalogue candidate and exact RF. Grouping requires both receivers, baseline
training joint candidate/signal probability >=0.5, and at least eight training
samples spanning ten seconds per member. There are 958 groups and 2,260 grouped
tracks across the nine panels.

Only the designated candidate component receives the correction. Other
candidate components, visibility priors and the q020 unassociated-trend
background remain present. Each group integrates the product of its track
mixtures under one common latent curvature; multiplying separate per-track
integrals would represent a different model. Per-track constant frequency is
still eliminated through the original normalized Student-t4 contrasts.

This extends the prior shared-slope research implementation with a fixed
training-only curvature basis and narrower same-RF, cross-RX membership.
It follows [cross-RX curvature transfer](../2026_09_29_curvature_transfer/README.md)
and the [information-retention audit](../2026_09_29_curvature_information/README.md).
The physical source of the shared residual remains unidentified.

## Validation and next step

All nine optimizer runs succeeded with no near-boundary solutions. Physical
gradient, finite-difference derivative and 128/256-node quadrature checks pass
the frozen gates. All processes exited zero within 12 seconds each, far below
the 180-second cap. Three workers ran concurrently.

Three tests cover the training-only basis, shared-product marginalization,
zero-curvature baseline recovery, numerical gradients and held-value mutation
isolation. Ruff passes. Input/source hashes and cached-baseline training scores
were replayed. Every raw fit and subprocess receipt is retained; no failed
case was dropped or rerun with tuned settings.

The next discriminating test is whole-receiver or whole-scan prediction with
this fixed prior and a baseline fitted to the same source split. The present
interleaved holdout is insufficient: earlier shared-slope models also improved
held prediction without reliable location gains. Do not increase the width
based on the current reference errors. If stronger holdout prediction and
paired geography improve, then test longer scan pools while retaining their
configured-center control and source/target separation.

The geographic reference is inherited, exposed and unsurveyed. Candidate banks
are site-conditioned, and timing/orbit truth is not independently calibrated.
These results do not establish blind or general sub-km accuracy. No RF,
production analyzer, QNAP path or golden fixture changed. Artifacts are local.

## Evidence and reproduction

See [protocol](PROTOCOL.md), [machine-readable summary](summary.json), model.py,
run.py and per-panel JSON for group membership, fitted parameters, held scores,
optimization diagnostics, quadrature audits and source hashes.

```bash
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python -m unittest discover -s reports/2026_09_29_shared_curvature -v
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python reports/2026_09_29_shared_curvature/batch.py
OPENBLAS_NUM_THREADS=1 .venv/bin/python reports/2026_09_29_shared_curvature/summarize.py
uv run --no-project --with matplotlib python reports/2026_09_29_shared_curvature/plot.py
```

Archive the completed run before reproduction: receipts and summary use
exclusive creation, while per-panel numerical outputs would be overwritten.
