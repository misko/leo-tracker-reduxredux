# DS1 iteration 26: rate-marginalized fixed-anchor smoke

## Decision

**No-go.** The sealed nine-cell 48.828125 m stencil was not run. The fixed-anchor smoke failed one mandatory numerical gate: the five-node quartic phase surrogate differed from exact causal SGP4 by **0.3941704476 Hz**, above the sealed **0.2 Hz** limit. This is a numerical-surrogate rejection of this iteration, not evidence against the rate-marginalized model or the anchor.

The plan was sealed before output. It fixes the iteration-10 anchor `(37.85822833, -122.47896246)`, group taus `-0.75/-0.50 s`, weights `0.2742/0.7258`, original randomized TRAIN only, hard association at the anchor, unsupported tracks at cap, per-track profiled TRAIN CFO, pseudo-Huber scale 250 Hz, Gaussian rate sigma `0.09176615913014215 s/h`, and the untouched nine-cell stencil. Neither truth nor HELD values entered association, fitting, scoring, gates, or the decision.

## Worked

The deterministic posterior calculation was stable. The pooled posterior-expected cap-800 score was `0.0646599402873291` on the fine 16-sigma rule. Its exact repeat was identical. Coarse/fine disagreement was `1.7156e-9`; 12-sigma/16-sigma disagreement was `1.1195e-11`; the largest transformed-tail mass was `6.74e-58`. All are comfortably inside their sealed gates.

The exact-material expected-score correction also passed: the hybrid score uses exact losses at every discrete posterior node with mass at least `1e-6` and surrogate losses only at sub-threshold nodes. Exact minus full-surrogate expected score was `-9.8049e-11`, versus the `1e-4` limit. This hybrid definition does not renormalize material mass.

The anchor selected 476 supported tracks and 117 sources from 4,785 TRAIN observations in group `20260921_00`, and 298 tracks and 133 sources from 5,692 TRAIN observations in group `20260921_16`. No track was unsupported at this anchor. Session losses were occupied-second weighted, sessions were equal within each group, and the frozen group weights were then applied.

Source 68739 was resolved explicitly. Its main refined mode was `0.5750151883 s/h`, posterior mean `0.5750805305 s/h`, and posterior standard deviation `0.0072839530 s/h`. Exact replay covered 107 posterior-material nodes plus zero and both refined modes; its largest error was `0.0007183 Hz`, so 68739 was not the blocker. The artifact also records all 88 sparse cases (four or fewer observations or one track), including their modes, posterior summaries, tails, and exact-node audits.

## Failed

Three secondary refined modes violated the exact-SGP4 limit:

| Group | Source | Secondary rate (s/h) | Max phase (s) | Max error (Hz) |
|---|---:|---:|---:|---:|
| 20260921_00 | 60096 | 1.2905164937 | 54.7189375 | 0.3941704 |
| 20260921_00 | 60400 | 0.7389075763 | 48.6820033 | 0.3501512 |
| 20260921_16 | 65396 | -1.4258684900 | 53.7660841 | 0.3183118 |

The limiting source 60096 has 32 TRAIN observations in four tracks. Its primary mode at `0.0406748032 s/h` reaches only `1.7246444 s` phase and has `1.23e-6 Hz` maximum replay error. The failure occurs at the secondary refined mode with energy `408.4917`, where the 54.72-second phase lies far outside the phase nodes at `-2,-1,0,+1,+2 s`. Even though that mode has negligible posterior probability, the sealed design requires every refined mode to meet the exact gate; it cannot be discarded after seeing the result.

## Learned

Dense log quadrature, mode enumeration, tails, and expected-loss marginalization are computationally practical here: the final sequential single-thread smoke took `78.09 s`, well below the external 1,800-second timeout. Four workers were allowed but unused because the minimal anchor smoke completed quickly and deterministic sequential execution reduced implementation risk.

The existing quartic surrogate is excellent near the posterior mass, including the scientifically prominent 68739 mode. Its extrapolation is not uniformly valid across every remote local minimum admitted by a 16-sigma all-mode scan. Expected-score agreement alone would have hidden that limitation because the failed modes carry essentially no posterior mass; the explicit all-mode exact gate did its job.

## Next

Iteration 27 should expand the exact/surrogate phase support before any geographic lattice. A suitable predeclared repair is either denser exact phase nodes covering the largest enumerated mode phase or direct batched exact SGP4 evaluation for refined modes and material quadrature nodes. It should repeat this same fixed-anchor smoke and preserve all thresholds. Only a passing replay gate should unlock the already defined nine-cell stencil, exact/surrogate winner comparison, numerical gap test, and all 12 leave-one-session center reranks.

## Reproduction

Run the component tests and the sealed smoke with single-thread math and an external hard timeout:

```bash
env OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 OMP_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  .venv/bin/pytest -q reports/2026_09_25_ds1_iteration26_rate_marginal/test_run.py

env OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 OMP_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  timeout --signal=TERM 1800s .venv/bin/python \
  reports/2026_09_25_ds1_iteration26_rate_marginal/run.py \
  --stage smoke --output /tmp/ds1-iteration26-smoke.json
```

The permanent machine-readable records are `plan.json`, `smoke.json`, and `checkpoint.json`, each with a SHA-256 sidecar. The smoke artifact contains every per-source mode/tail summary, all sparse-case details, every session score, provenance bindings, and the exact material-node audit.
