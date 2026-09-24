# DS1 iteration 12: shared per-NORAD causal-rate fit

## Question

Can the two DS1 six-scan TRAIN groups constrain a common causal orbit-rate
correction for the same satellite, while retaining an independent constant CFO
for every RF track?  This is a local, reference-free continuation of the
sealed iteration-10 coordinate and group-specific timing pair.

## Method

The authoritative default run is a frozen-exact-support equivalence ablation:

1. load the sealed, reference-free iteration-10 winning coordinate, its
   group-specific times (`-0.75 s` for `20260921_00`, `-0.50 s` for
   `20260921_16`), hard associations, exact rate maps, losses, and replay
   gates;
2. enumerate the selected NORAD source sets in both groups;
3. merge the two exact rate maps into one map indexed only by NORAD; and
4. verify that a NORAD appearing in both groups would receive one shared
   correction, then report the exact balanced loss and inherited replay gates.

When those source sets are disjoint, as they are here, the joint rate vector
is block diagonal.  The merge is therefore mathematically equivalent to the
two prior exact fits, and re-optimizing cannot create a cross-group constraint.

An optional `--fresh-exact-refit` path implements the broader experiment: it
reacquires all hard associations on a symmetric 3x3, 48.828 m lattice,
rebuilds exact causal-SGP4 phase supports, profiles one bounded rate per
NORAD and a CFO per track, ranks locations by balanced cap-800 loss, and
requires exact replay gates.  It is intended only for a bundle that actually
contains repeated selected NORADs across groups.

The location seed, time values, and every support are RF-selected.  The true
coordinate is only introduced by `evaluate_postseal.py` after selection.

## Result

The selected exact supports contain 237 NORADs: 109 in group `20260921_00`
and 128 in group `20260921_16`.  Their intersection is **zero**.  Therefore
the proposed shared-NORAD rate vector has no cross-group parameter to share on
this DS1 pair.  Its objective is block diagonal and exactly reproduces the
sealed independent-rate result:

| Quantity | Value |
| --- | ---: |
| Balanced exact cap-800 loss | 0.0581276592 |
| Group 00 exact replay gate | pass |
| Group 16 exact replay gate | pass |
| Cross-group shared NORADs | 0 |
| Post-seal position error | 1.179286 km |

The authoritative inference is deliberately a frozen-exact-support ablation,
not a new 3x3 geographic search.  A fresh exact 3x3 refit is implemented
behind `--fresh-exact-refit`, but the zero overlap proves it cannot introduce
the desired cross-group constraint on this bundle; its expensive numerical
rate profile would only reproduce separate group fits.  The fast ablation is
the more direct test of the hypothesis.

The inference JSON records merged rate maps, group source sets, associations,
and the inherited exact replay gates.  `evaluation/iteration12-postseal.png`
is the requested PNG; the JSON and CSV in that directory include the separate
reference-only error calculation.

## Reproduction

```bash
.venv/bin/python -m pytest -q reports/2026_09_24_ds1_iteration12_shared_norad/test_run.py
.venv/bin/python reports/2026_09_24_ds1_iteration12_shared_norad/run.py \
  --output reports/2026_09_24_ds1_iteration12_shared_norad/inference.json
.venv/bin/python reports/2026_09_24_ds1_iteration12_shared_norad/evaluate_postseal.py \
  --inference reports/2026_09_24_ds1_iteration12_shared_norad/inference.json \
  --output-dir reports/2026_09_24_ds1_iteration12_shared_norad/evaluation
```

`inference.json` is TRAIN-only and reference-free.  `evaluation/` is a
separate post-seal artifact.  The inference file records exact code and input
hashes, all candidate rows, rate maps, associations, and gate results.

Use `--fresh-exact-refit --workers 4` only on a bundle whose selected source
sets overlap.  A productive next DS1 iteration is therefore to choose scans
that revisit common NORADs, then fit their shared rate correction across those
visits.  The current 00/16 groups cannot test that benefit.
