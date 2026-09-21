# Sparse-position exploration checkpoint

This bounded single-site replay finds conditional sub-kilometre solutions after
changing sparse-observation membership. It does **not** establish sub-kilometre
accuracy. Identities come from earlier full-archive analysis. Convergence and
exact-propagation agreement are required before an error is qualified.

## Complete initial experiments

| Intervention | Budget | Converged | Exact pass / checked | Qualified sub-km | Qualified error min / median / max |
|---|---:|---:|---:|---:|---:|
| Original memberships, Gaussian fixed 250 Hz | 399 | 2/3 | 2/2 | 0/3 | 2,288 / 2,903 / 3,517 m |
| Original memberships, Gaussian fixed 250 Hz | 798 | 3/3 | 2/3 | 0/3 | 1,167 / 1,696 / 2,226 m |
| Original memberships, Gaussian fixed 250 Hz | 1,597 | 2/3 | 1/2 | 0/3 | 1,632 / 1,632 / 1,632 m |
| Original memberships, Gaussian learned scale | 399 | 0/3 | 0/0 | 0/3 | — m |
| Original memberships, Gaussian learned scale | 798 | 0/3 | 0/0 | 0/3 | — m |
| Original memberships, Gaussian learned scale | 1,597 | 0/3 | 0/0 | 0/3 | — m |
| Original memberships, Student fixed 250 Hz | 399 | 3/3 | 2/3 | 0/3 | 2,241 / 2,752 / 3,264 m |
| Original memberships, Student fixed 250 Hz | 798 | 2/3 | 2/2 | 0/3 | 1,264 / 1,702 / 2,140 m |
| Original memberships, Student fixed 250 Hz | 1,597 | 3/3 | 2/3 | 0/3 | 1,640 / 1,886 / 2,132 m |
| Packet 3, formal | 399 | 3/3 | 3/3 | 2/3 | 415 / 642 / 1,258 m |
| Packet 3, formal | 798 | 3/3 | 3/3 | 3/3 | 675 / 919 / 954 m |
| Packet 3, formal | 1,597 | 1/3 | 1/1 | 1/3 | 548 / 548 / 548 m |
| Packet 3, Gaussian fixed 250 Hz | 399 | 3/3 | 0/3 | 0/3 | — m |
| Packet 3, Gaussian fixed 250 Hz | 798 | 3/3 | 0/3 | 0/3 | — m |
| Packet 3, Gaussian fixed 250 Hz | 1,597 | 3/3 | 0/3 | 0/3 | — m |
| Packet 5, formal | 399 | 3/3 | 3/3 | 0/3 | 1,015 / 1,077 / 1,528 m |
| Packet 5, formal | 798 | 3/3 | 3/3 | 1/3 | 896 / 1,031 / 1,038 m |
| Packet 5, formal | 1,597 | 3/3 | 3/3 | 3/3 | 351 / 541 / 836 m |
| Packet 5, Gaussian fixed 250 Hz | 399 | 3/3 | 1/3 | 0/3 | 2,211 / 2,211 / 2,211 m |
| Packet 5, Gaussian fixed 250 Hz | 798 | 3/3 | 0/3 | 0/3 | — m |
| Packet 5, Gaussian fixed 250 Hz | 1,597 | 3/3 | 0/3 | 0/3 | — m |

Failures remain in every denominator. Missing exact checks never count as passes.

## Completed 20-seed replication

| Intervention | Budget | Converged | Exact pass / checked | Qualified sub-km | Qualified error min / median / max |
|---|---:|---:|---:|---:|---:|
| Packet 3, formal (20 seeds) | 399 | 17/20 | 17/17 | 9/20 | 117 / 953 / 1,932 m |
| Packet 3, formal (20 seeds) | 798 | 11/20 | 11/11 | 7/20 | 216 / 934 / 1,704 m |
| Packet 3, formal (20 seeds) | 1,597 | 2/20 | 2/2 | 2/20 | 548 / 623 / 698 m |
| Packet 5, formal (20 seeds) | 399 | 17/20 | 17/17 | 7/20 | 421 / 1,077 / 2,285 m |
| Packet 5, formal (20 seeds) | 798 | 20/20 | 20/20 | 11/20 | 31 / 937 / 1,940 m |
| Packet 5, formal (20 seeds) | 1,597 | 14/20 | 14/14 | 12/20 | 142 / 554 / 1,273 m |

All 81 converged fits pass exact verification; 39 of 120 remain nonconverged.
Packet-3 convergence falls from 17/20 at 399 observations to 2/20 at 1,597.
Packet-5 reaches 20/20 at 798 observations, with 11/20 qualified sub-kilometre.
These are conditional single-site rates.

## Distinct interventions

The paired comparison holds seed, budget, archived identity mapping, and
evaluation policy fixed while changing sampling membership. The selected source
subset changes. Noise-family and solver changes are separate interventions.

The historical comparator is available (9 matched original-density rows; kept descriptive because solver and model interventions differ). Student fixed-noise restores
convergence in 8/9 initial runs, but errors remain 1.26–3.26 km.

## Completed numerical experiments

| Evaluation | State | Complete results | Scored here |
|---|---|---:|---:|
| 20-seed packet-formal replication | complete and exact-checked | 120/120 | yes |
| Stabilized same-likelihood solver | complete; 0/9 converged | 9/9 | no |
| Gaussian contrast model | complete and exact-checked | 9/9 | yes |
| Geometry analysis | complete and exact-checked | 3/3 | yes |
| Laplace contrast follow-up | complete and exact-checked | 9/9 | yes |

| Intervention | Budget | Converged | Exact pass / checked | Qualified sub-km | Qualified error min / median / max |
|---|---:|---:|---:|---:|---:|
| Gaussian contrast | 399 | 2/3 | 1/2 | 0/3 | 3,008 / 3,008 / 3,008 m |
| Gaussian contrast | 798 | 1/3 | 1/1 | 1/3 | 709 / 709 / 709 m |
| Gaussian contrast | 1,597 | 2/3 | 1/2 | 1/3 | 536 / 536 / 536 m |

Gaussian contrast has three exact-qualified fits among nine planned runs. Two
are sub-kilometre. Four nonconverged runs and two exact failures remain.

| Intervention | Budget | Converged | Exact pass / checked | Qualified sub-km | Qualified error min / median / max |
|---|---:|---:|---:|---:|---:|
| Geometry-Fisher, formal | 399 | 1/1 | 1/1 | 0/1 | 1,089 / 1,089 / 1,089 m |
| Geometry-Fisher, formal | 798 | 1/1 | 1/1 | 1/1 | 660 / 660 / 660 m |
| Geometry-Fisher, formal | 1,597 | 0/1 | 0/0 | 0/1 | — m |

Both converged geometry-Fisher fits pass exact propagation. The 798-observation
case has 660 m error. The 1,597-observation fit remains failed despite its 287 m
coordinate. A bounded diagnostic locates failure in Student-t nuisance
reweighting at high sparse-nuisance dimension. It does not qualify the failed
fit.

| Intervention | Budget | Converged | Exact pass / checked | Qualified sub-km | Qualified error min / median / max |
|---|---:|---:|---:|---:|---:|
| Laplace contrast | 399 | 2/3 | 2/2 | 0/3 | 1,607 / 1,628 / 1,649 m |
| Laplace contrast | 798 | 0/3 | 0/0 | 0/3 | — m |
| Laplace contrast | 1,597 | 2/3 | 1/2 | 0/3 | — m |

Laplace converges in 4/9 runs. Two 399-observation fits qualify, at 1.61 and
1.65 km. The exact-passing 405 m candidate hits a rate boundary, invalidating
the zero-gradient Laplace assumption, so it is unqualified. Reliable
sub-kilometre performance at 399 observations remains unresolved.

## Why sparse sampling failed

With seed 0 at 1/32, ordinary thinning keeps 399 observations across 320 tracks.
Of those tracks, 248 have one observation and only seven have three or more.
A free frequency offset absorbs a singleton completely: it supplies no
within-track Doppler shape. Three-point sampling uses the same 399 observations
across 133 tracks, all with three separated points.

| Seed 0, 399 observations | Tracks | Singletons | Offset-free contrasts |
|---|---:|---:|---:|
| Ordinary thinning | 320 | 248 | 79 |
| Three-point packets | 133 | 0 | 266 |
| Five-point packets | 80 | 0 | 319 |

Gaussian contrast integrates out track frequency offsets, removing noise-scale
information incorrectly retained by singleton profiles. Its fitted noise is
about 40–77 Hz; the rate-marginal variant gives 73–96 Hz, rather than collapsing
toward the 5 Hz floor. This fixes a modeling pathology but does not establish
a reliable location estimator.

The geometry experiment's 1/8 failure is in the inner robust nuisance solve:
both outer location optimizations succeed, but nuisance reweighting exhausts
60 iterations with 533 offsets and 382 phase-rate corrections. No correction
reaches its bound. More data can therefore increase numerical difficulty even
while improving the available geometric information.

## Reproduction and scope

```bash
artifact_dir=reports/artifacts/2026_09_21_sparse_position_exploration
.venv/bin/python tools/report_sparse_position_exploration.py \
  --noise ${artifact_dir}/noise-evaluation.json \
  --noise-exact ${artifact_dir}/noise-exact.json \
  --shape ${artifact_dir}/shape-initial-evaluation.json \
  --shape-exact ${artifact_dir}/shape-initial-exact.json \
  --twenty-seed-evaluation ${artifact_dir}/shape-20seed-evaluation.json \
  --twenty-seed-exact ${artifact_dir}/shape-20seed-exact.json \
  --stabilized ${artifact_dir}/stabilized-results.json \
  --contrast ${artifact_dir}/gaussian-contrast-results.json \
  --contrast-exact ${artifact_dir}/gaussian-contrast-exact.json \
  --geometry ${artifact_dir}/geometry-evaluation.json \
  --geometry-exact ${artifact_dir}/geometry-exact.json \
  --laplace ${artifact_dir}/laplace-contrast-results.json \
  --laplace-exact ${artifact_dir}/laplace-contrast-exact.json \
  --output-dir reports/2026_09_21_sparse_position_exploration \
  --report reports/2026_09_21_sparse_position_exploration.md
```

Frozen plans, job packets, checks and source receipts are in the
[artifact directory](artifacts/2026_09_21_sparse_position_exploration/).
The exact executed stabilized-solver source was not recovered; its receipt
distinguishes the retained later diagnostic revision. Its negative 0/9 result
is descriptive, not an exactly reproducible source checkpoint.

Budgets are 399, 798, and 1,597 existing training-pool observations. Truth did
not fit the model or select a run. Full-archive identities mean this does not
demonstrate blind acquisition. Independent sites are still required.

The next numerical step is a scalar per-source solve replacing the joint inner
IRLS system, while retaining the convergence tolerance. Accuracy calibration
requires independent sites.

Validation: 31 targeted tests passed, covering the frozen formal model,
subset invariants, held-out isolation, scalar integration checks and report
qualification. Ruff and whitespace checks passed. These are isolated research
modules; the existing production positioning model was not changed.
