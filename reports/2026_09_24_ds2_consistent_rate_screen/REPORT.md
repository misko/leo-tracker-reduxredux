# DS2 consistent cap-800 and causal-rate local screen

This closes two DS2 conditional-model gaps using the frozen 20-capture
September 24 corpus. Both inferences begin with the already sealed,
reference-free, all-20 winner from the Sacramento 250 km prior. The geographic
reference was not available to either inference and enters only in
`postseal-evaluation.json`.

The bounded scope is deliberate. A fresh 250 km rate-aware or matched
cap-800 recomputation would require rebuilding every candidate prediction and
exact replay at that scale. Instead, each model evaluates a 3 by 3 local grid
with 195.3125 m spacing around the sealed RF-only winner. This is a local
comparison and refinement, not a new independent wide-prior result.

## Results

| Method | Selected cell | RF selection score | Exact replay | Post-seal error |
| --- | --- | ---: | --- | ---: |
| Parent, full-observation causal-rate (previous sealed result) | parent centre | 0.05184 | passed | 1.924 km |
| Consistent cap-800 proposal plus exact selection | 195 m west | 0.05393 exact capped loss | both chronological-group gates passed | **1.735 km** |
| Nominal matched local control | 195 m west, 195 m north | 0.09322 cached capped loss | passed | 1.798 km |
| Rate-aware local screen | same cell as nominal control | 0.09322 cached capped loss | passed | 1.798 km |

The cap-800 result is the better of the two additions: it improves the sealed
parent by 189 m on this post-seal reference calculation. It fits rate nuisance
parameters on all qualified observations, but selects locations using the
same cap-800, duration-weighted loss used by its exact comparison. The exact
loss is higher than its cached proposal loss (0.05393 versus 0.04766), so the
proposal remains a screen and the exact audit remains the published decision.

The rate-aware screen did **not** produce a different result from its nominal
control. At all nine cells its rate fit was rejected by the published
rate-plus-prior screen objective, so the selected objective reduced exactly to
the nominal capped loss. This is useful negative evidence: with these
receipt-bound cached sensitivities, a one-reassignment causal-rate surrogate
does not add local geographic separation here. It should not be promoted as a
replacement for exact rate fitting.

![Bounded nominal and rate-aware screen](/home/mouse9911/gits/leo-adaptive-position-deploy/reports/2026_09_24_ds2_consistent_rate_screen/rate-screen-objective.png)

## Method and reproducibility

`cap800-run-manifest.json` partitions all 20 whole sessions in chronological
order into two disjoint ten-session groups with equal objective weight. It
uses cached DS2 evidence, three global timing candidates (-1, 0, +1 s), and
the shared sealed parent centre. There are 54 cached supports (nine cells,
two groups, three timing values), two retained basins, and eight exact SGP4
audits. The cache/checkpoint root is external and read-only for the report;
the report binds its input receipts and modules by digest.

`rate-screen.json` independently reacquires hard satellite candidates at each
of its nine cells. The experimental arm fits a causal rate per NORAD,
reacquires once with that rate, then refits. The matched control uses the
nominal hard support at the same cell. Each winner has an exact SGP4 replay
gate: maximum replay errors are 21.80 microhertz and the gates pass at their
0.2 Hz tolerance. These numerical replay gates validate the exact
implementation's agreement with its local approximation; they do not turn
candidate identities or fitted receiver phase into calibrated geometric
claims.

Reproduce from the repository root:

```bash
.venv/bin/python reports/2026_09_24_ds2_consistent_rate_screen/build_cap800_manifest.py \
  --cache-root /var/tmp/leo-ds2-portable-cache
.venv/bin/python reports/2026_09_24_ds2_consistent_cap800_runner/runner.py \
  --manifest reports/2026_09_24_ds2_consistent_rate_screen/cap800-run-manifest.json \
  --work-root /var/tmp/leo-ds2-cap800-consistent-local \
  --output reports/2026_09_24_ds2_consistent_rate_screen/cap800-inference.json --workers 2
.venv/bin/python reports/2026_09_24_ds2_consistent_rate_screen/run_rate_screen.py \
  --cache-root /var/tmp/leo-ds2-portable-cache --workers 2
.venv/bin/python reports/2026_09_24_ds2_consistent_rate_screen/postseal.py
```

The focused tests cover the rate-screen grid and arm scoring, the portable
cache port, cache receipt integrity, immutable checkpoints, warm starts, and
frozen-manifest validation.
