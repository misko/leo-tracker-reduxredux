# DS1 iteration-8 joint prefix-6 receiver position

## Result

The sealed joint fit selected one shared receiver coordinate:
`(37.86086011, -122.48174033)` degrees. Its balanced exact cap-800 loss was
`0.05825069`, the equal-weight mean of independent group losses of `0.03899473`
for `20260921_00` and `0.07750664` for `20260921_16`. Both groups selected
their own tau at `-0.75 s`; their hard associations, per-NORAD rates, and
per-track CFOs remained independent.

The result is sealed in `inference.json` before the reference comparison. The
separate post-seal evaluator measured a 1.3593 km geographic error. Truth did
not enter the spatial union, fixed tau-grid screen, proposal selection, exact
audits, or winner selection.

## Method and bound

Iteration 8 consumes the completed reference-free iteration-6 exact candidate
artifact and deduplicates its 56 group/tau rows to 16 immutable coordinates.
It cross-evaluates **both** groups at every coordinate on the same fixed tau
grid `[-2.25, -2.00, ..., -0.25] s`. For each group/tau, it rebuilds the full
qualified RF support and profiles a cap-300 proposal with that group's own
hard association, NORAD phase rates, and track CFOs.

At a coordinate, the proposal score is:

```text
0.5 * best_group_00_cap300_objective + 0.5 * best_group_16_cap300_objective
```

Thus neither group can dominate simply because it supplies more observations.
The bounded exact stage retained the eight best joint coordinates, then
audited the two best proposal taus separately for each group: 32 exact SGP4
fits in total. A coordinate's final score is the equal-weight mean of the two
groups' best exact cap-800 losses. Selection never pools observations or
shares timing/rates/CFOs.

The full run used four workers, completed 32 grid scans and 32 exact audits in
855.95 seconds (14.27 minutes), and stayed within the one-hour limit. All 32
exact SGP4 comparison gates passed; the winner's maximum cache/exact Doppler
discrepancies were `5.10e-05 Hz` (00) and `5.82e-05 Hz` (16), both far below
the 0.2-Hz gate.

## What worked, what did not, and next

The joint screen and exact ranking agree on a compact eastern candidate set.
The exact winner is 0.0000991 balanced-loss below the runner-up, and the
winning tau is independently selected by both groups. This shows that a shared
location can be tested without allowing the larger 16 group to overwhelm the
00 loss by raw observation count.

The final eight exact candidates are close: the candidate union remains a
coarse, inherited spatial set, and the small winner margin does not establish
sub-kilometre identifiability. The selection also retains only two tau
proposals per group and does not rerun a continuous spatial refinement. Those
are deliberate runtime and anti-selection-leakage bounds, not evidence that
other spatial/timing values are excluded.

The next reference-free experiment should freeze this joint winner and its
seven nearest union coordinates, then add a predeclared local sub-kilometre
spatial lattice with the same equal-group objective and bounded exact audit.
It should report random whole-session validation splits before any further
post-seal comparison.

## Artifacts and reproduction

- `inference.json.gz` is the deterministic gzip copy of the sealed
  machine-readable inference record stored in the repository. Decompress it
  to `inference.json` for the replay and export commands below.
- `inference/iteration8-inference-finalists.csv` and
  `inference/iteration8-inference-finalists.png` summarize its exact finalists
  without truth.
- `evaluation/iteration8-postseal.json`, `.csv`, and `.png` are the separate
  truth-only post-seal comparison.

```bash
.venv/bin/python -m pytest -q reports/2026_09_24_ds1_iteration8_joint_groups/test_run.py
.venv/bin/python reports/2026_09_24_ds1_iteration8_joint_groups/run.py \
  --output reports/2026_09_24_ds1_iteration8_joint_groups/inference.json --workers 4
.venv/bin/python reports/2026_09_24_ds1_iteration8_joint_groups/export_inference_artifacts.py \
  --inference reports/2026_09_24_ds1_iteration8_joint_groups/inference.json \
  --output-dir reports/2026_09_24_ds1_iteration8_joint_groups/inference
.venv/bin/python reports/2026_09_24_ds1_iteration8_joint_groups/evaluate_postseal.py \
  --inference reports/2026_09_24_ds1_iteration8_joint_groups/inference.json \
  --output-dir reports/2026_09_24_ds1_iteration8_joint_groups/evaluation
```
