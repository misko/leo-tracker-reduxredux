# Do early-symbol partitions persist when DS10 is added?

All original early-symbol observations were aligned by unique observation ID
between the DS7/8/9 and DS7/8/9/10 artifacts. The original feature vectors are
**exactly unchanged**, not merely numerically close. This isolates the effect
of adding observations from recalibration or a change in their symbol values.
Both expanded linkage arrays were also reproduced from their saved features.

| Edge | Original entries | Added DS10 entries | ARI at 2 / 4 / 8 groups after extension |
|---|---:|---:|---|
| Upper | 252 | 186 | 0.504 / 0.509 / 0.444 |
| Lower | 486 | 470 | 0.565 / 0.348 / 0.149 |

ARI compares group membership of the original observations only and is invariant
to renaming groups. The added counts reproduce the original 1,394-entry combined
tree, before the later one-entry deduplication. No extra DS7/8/9 observations
were introduced in this alignment.

![Four-group membership before and after adding DS10](local/corpus-extension.png)

The four-group partitions are highly imbalanced: original upper group sizes are
236, 9, 3 and 4; lower sizes are 469, 12, 4 and 1. Most observations remain in
the large group. Changes are concentrated in small branches; a low ARI must not
be read as that fraction of all observations changing groups. For example, 231
of the 236 upper large-group members remain together, as do 468 of the 469 lower
large-group members. The figure preserves counts to make this distinction clear.

## Whole-session sensitivity control

For each edge, repeat 99 times with half the additional recording sessions,
retaining all their observations together. The upper additions cover 64 sessions
and the lower additions 74. Each control keeps every original observation and
adds whole sessions selected without reference to satellite labels or header
outcomes. Upper control samples add 78–112 entries, lower 183–302.

Median ARI at 2/4/8 groups is 0.479/0.525/0.365 for upper and
0.435/0.333/0.305 for lower. Thus sensitivity is not confined to the single full-
extension choice. These are descriptive composition controls, not permutation
p-values or new independent trials. No number of groups was chosen afterward
for favorable agreement; all three fixed cuts are retained.

## Firmware interpretation

The earlier input-order audit established numerical stability of these early
trees. This test establishes a different limitation: their small branches depend
on the corpus included. Neither finding shows an RF-to-software mapping.

A four-group cut cannot be assigned directly to the audited two-bit prefix field.
The firmware has mode-dependent field presence, and the observed tree produces
one dominant group plus small branches whose membership changes after extension.
Unequal firmware-state frequencies are possible, so imbalance alone is not a
falsification of that field interpretation. A defensible mapping would have to
predict state values and changes on held-out observations, control receiver/time/
channel effects and distinguish known waveform structure. Those conditions are
not satisfied by these dendrograms.

This experiment does not reject hidden header fields or satellite information.
It narrows what may be inferred from the existing cluster topology. No RF bits
were decoded, no firmware field was assigned and no identity labels were used
to construct or select the partitions.

## Reproduction

`corpus_extension.py` verifies feature identity and saved trees, records complete
session controls, contingency tables and source/method hashes, and generates the
figure. Outputs remain ignored in `local/`. Its focused test rejects duplicate
and missing IDs and checks exact observation alignment; it and Ruff pass.

```sh
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy --with matplotlib python reports/2026_09_29_firmware_cluster_reaudit/corpus_extension.py
uv run --no-project --with numpy --with scipy --with pytest pytest -q reports/2026_09_29_firmware_cluster_reaudit/test_corpus_extension.py
```

No new RF, fixture update, production-code change or data commit was made. The
remaining association ledger and firmware-derived held-out tests remain in progress.
