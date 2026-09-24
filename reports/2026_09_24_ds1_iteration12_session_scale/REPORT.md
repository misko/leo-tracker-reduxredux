# DS1 iteration 12: converged regularized session-scale arm

## Question

Iteration 6B tested whether a fractional Doppler-scale hierarchy could remove
part of DS1's positional bias.  Its joint finite-difference optimizer reached
its function-evaluation limit at every candidate, so its apparently better
losses were rejected.  This iteration retests the same physical nuisance
model with a convergent block-coordinate fit and a matched rate-only baseline.

## Predeclared inference contract

The driver consumes only the sealed, reference-free iteration-10 winner.  It
uses its independent group taus (`-0.75 s` for `20260921_00`, `-0.50 s` for
`20260921_16`) and its selected hard associations.  It reconstructs the exact
SGP4 support for a symmetric 3×3 lattice centered on that coordinate, with
195.3125 m spacing.  The coordinate and support selection do not read a
reference coordinate.

At every group-coordinate support, both fits profile a bounded causal phase
rate per NORAD and an independent constant CFO per track.  The hierarchy also
fits one common fractional Doppler scale plus one session deviation per
session.  Both scale prior standard deviations are 500 ppm; every scale is
bounded at ±2,000 ppm.  Its selection score is exact cap-800 track-weighted
loss plus `0.001` times the rate-and-scale Gaussian penalty.  Group scores are
equally weighted.

The block procedure alternates:

1. bounded scalar robust fits for each NORAD rate after the scale is fixed;
2. an analytic-gradient L-BFGS-B update for the common-plus-session scale
   block after rates are fixed.

It stops only when both its selection-objective change is at most `1e-7` and
its largest parameter change is at most `2e-7`, or after 16 declared outer
iterations.  Opposite ±400 ppm scale starts are rerun at the selected point.

## Result

Level one selected the southwest edge of its 195.3125 m lattice:
`(37.85647382, -122.48118468)` degrees, or 195.3125 m west and south of the
iteration-10 origin.  Its hierarchy exact loss was `0.056944266`, lower than
the matched rate-only `0.058038435`.  Both methods selected the same point.
The separate post-seal evaluator measured `0.915761 km` error there.

Because this was an RF-selected lattice edge, a second sealed inference used
that point as its only origin and evaluated a fresh 97.65625 m symmetric 3×3
lattice.  It again selected the southwest edge:
`(37.85559656, -122.48229576)` degrees, 97.65625 m west and south of the
level-one winner.  The scale hierarchy exact loss improved to `0.056915864`
(`0.057999082` for its matched rate-only baseline).  Its post-seal error is
**`0.787188 km`**, a 128.573 m reduction from level one and the first robust
joint DS1 result below one kilometre in this sequence.

The matched rate-only baseline selected exactly the same level-one and
level-two coordinates.  The sub-kilometre coordinate therefore comes from the
predeclared expanded exact local search, not from adding the scale hierarchy.
The scale hierarchy improves loss at that coordinate, but has not yet supplied
evidence that it improves location selection.

The hierarchy improves the selected exact capped loss in both groups:

| Group | level-2 rate-only loss | level-2 hierarchy loss | reduction | outer iterations |
| --- | ---: | ---: | ---: | ---: |
| `20260921_00` | 0.038813477 | 0.037323570 | 0.001489907 | 14 |
| `20260921_16` | 0.077184687 | 0.076508158 | 0.000676529 | 15 |

No selected scale reached its guard and no rate reached its phase-rate bound.
At level two, the common scales were +429.8 ppm and -143.6 ppm; session
deviations ranged from -1,491 to +1,376 ppm, remaining inside the ±2,000 ppm
guard.  This is a useful residual model but also a warning that the session
terms are materially active; the result needs validation on independent scan
bundles before treating the position gain as calibrated.

The two level-one ±400 ppm initialization checks agreed on selection objective
to `2.40e-08` (group 00) and `3.24e-08` (group 16), and on capped loss to less
than `5e-10`.  The two group-00 alternate starts did not meet the strict
16-iteration outer stopping threshold despite this agreement; the selected
zero-start fit did converge in 14 iterations.  The initialization check is
therefore evidence of a shared numerical basin, not an independent
convergence certificate.

Level one took 519.44 s and the refinement 305.41 s using four workers.  The
refinement winner is again at an edge, so another predeclared symmetric level
would be required to claim a local spatial minimum.  The present result shows
a directional trend, not sub-100 m identifiability.

## Acceptance rule

The arm is portable only if its selected scale fit converges for both groups,
no selected scale touches the ±2,000 ppm guard, neither group's matched exact
capped loss worsens against its rate-only fit, and the two initialization
directions agree within `1e-6` on selection objective.  A lower training loss
alone is insufficient.

## Artifacts and reproduction

```bash
.venv/bin/python -m pytest -q reports/2026_09_24_ds1_iteration12_session_scale/test_run.py
.venv/bin/python reports/2026_09_24_ds1_iteration12_session_scale/run.py \
  --output reports/2026_09_24_ds1_iteration12_session_scale/inference.json --workers 4
.venv/bin/python reports/2026_09_24_ds1_iteration12_session_scale/evaluate_postseal.py \
  --inference reports/2026_09_24_ds1_iteration12_session_scale/inference.json \
  --output-dir reports/2026_09_24_ds1_iteration12_session_scale/evaluation
.venv/bin/python reports/2026_09_24_ds1_iteration12_session_scale/refine.py \
  --output reports/2026_09_24_ds1_iteration12_session_scale/refinement.json --workers 4
.venv/bin/python reports/2026_09_24_ds1_iteration12_session_scale/evaluate_refinement_postseal.py \
  --level1 reports/2026_09_24_ds1_iteration12_session_scale/inference.json \
  --refinement reports/2026_09_24_ds1_iteration12_session_scale/refinement.json \
  --output-dir reports/2026_09_24_ds1_iteration12_session_scale/evaluation
```

`evaluate_postseal.py` is the only artifact that reads the reference
coordinate, and does so only after inference output exists.
