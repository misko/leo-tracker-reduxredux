# Early-symbol dendrograms survive input-order controls

The word-distribution tree's tie sensitivity must not be generalized to the
early-symbol trees. These use a different measurement: normalized phase profiles
over symbols 2–7 and four common nonpilot carriers, rather than distributions of
60-bit words. We audited all four saved edge-specific early trees directly.

For each tree, reproduce average linkage from its saved features and require
numerical agreement with the saved linkage array. Reorder identical observations
99 times using a fixed seed, rebuild the tree, restore observation identities,
and compare exact 2-, 4-, and 8-group cuts by adjusted Rand agreement (ARI).
No identity label or signal value is changed. This is a numerical invariance
test, not a permutation test of satellite identity or held-out classification.

| Saved hierarchy | Entries | Minimum ARI at 2 / 4 / 8 groups |
|---|---:|---|
| DS7/8/9 upper edge | 252 | 1 / 1 / 1 |
| DS7/8/9 lower edge | 486 | 1 / 1 / 1 |
| DS7/8/9/10 upper edge | 438 | 1 / 1 / 1 |
| DS7/8/9/10 lower edge | 956 | 1 / 1 / 1 |

All tested cuts are unchanged. This supports treating the early trees as stable
numerical summaries of those saved observations. It does not prove field
boundaries, a two-bit firmware enum, or satellite identity. In particular:

- The combined tree retains its original 1,394 entries, including the duplicate
  removed in the later 1,393-entry identity analysis. Reproducing the original
  tree requires retaining its exact inputs; this does not make them independent.
- The earlier 738-entry trees and later 1,394-entry trees use their own saved
  feature populations. This test does not measure whether adding DS10 preserves
  the old partitions. That requires an explicitly aligned cross-corpus comparison.
- Reordering is weaker than resampling frames or testing held-out receivers and
  visits. It probes tie handling, not noise robustness or generalization.
- Mode-dependent software prefix widths from the firmware audit still have no
  established mapping onto the 24 observed early coordinate locations.

`early_tree_audit.py` records full control scores, source hashes and its method
hash in ignored `local/early-tree-audit.json`. A focused test verifies observation
identity restoration using a synthetic untied tree. It passes, as does Ruff.

```sh
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python reports/2026_09_29_firmware_cluster_reaudit/early_tree_audit.py
uv run --no-project --with numpy --with scipy --with pytest pytest -q reports/2026_09_29_firmware_cluster_reaudit/test_early_tree_audit.py
```

The source catalog has also been expanded to nested tile, revisit, paired and
within-visit experiment receipts. This remains an artifact catalog; extracting
and testing every semantic association is ongoing. No new RF, golden-fixture
change or production change was made.
