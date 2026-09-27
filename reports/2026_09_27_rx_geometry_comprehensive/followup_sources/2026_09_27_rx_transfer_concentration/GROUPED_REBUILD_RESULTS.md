# Grouped, refitted RX association replay: small incremental predictive signal

## Outcome

The complete six-recording development replay supports an incremental RX
association signal **after matching geometry-free regularization**. It does not
establish improved geographic error or physical satellite identity. No search,
new RF acquisition, or production change occurred.

| Gain over matched regularized frequency baseline | X → Y | Y → X |
|---|---:|---:|
| Normal RX, occupied-second weighted | **+0.004056** | **+0.000994** |
| Normal RX, equal-recording average | +0.004235 | +0.000867 |
| Normal RX, recordings improving | 5/6 | 4/6 |
| Reversed RX, occupied-second weighted | −0.005221 | −0.004299 |
| Reversed RX, recordings improving | 1/6 | 0/6 |
| Candidate-independent null | approximately 0 | approximately 0 |

Positive means lower held-frequency NLL per observation. Directions refer to
randomized groups, not chronological early/late halves. The reciprocal results
are dependent and must not be pooled as independent replicates.

| Recording suffix | Supported / total tracks | Normal X → Y | Normal Y → X |
|---|---:|---:|---:|
| 39ac2b14d1bb5f0f | 51/62 | +0.005503 | +0.002174 |
| 4c56320fb5ca6994 | 39/60 | +0.002419 | −0.004470 |
| 9d7b6a0db558703a | 38/57 | +0.012789 | −0.001014 |
| aa9770c66396e928 | 44/55 | +0.001167 | +0.002728 |
| c559f436d578c9bd | 42/52 | +0.006129 | +0.002422 |
| da2858f6cd2521b7 | 45/58 | −0.002600 | +0.003365 |

Exactly 259 tracks support both partitions; 85 are reported unsupported rather
than silently dropped. Their observations do not enter the score. There are
518 reciprocal predictions and 6,401 / 6,373 held observations respectively.
These rows are not independent statistical samples.

## What was rebuilt

- Seed 20260927, session-wide 10-second UTC blocks, joined across raw-window
  overlap, common RX opportunities, and physical pairs. No frame-level shuffle.
- Full visible-catalogue top-three selection and robust constant CFO separately
  fitted on X and on Y. The old shortlist and old CFO were not reused.
- Reception outcomes extracted for all observations through the existing
  position-independent endpoint adapter. Newly chosen candidate directions
  were recomputed from the corresponding orbit bank.
- Each conditioning frequency likelihood enters once. X alone determines the
  X→Y candidate weights, CFO, and reception update; held Y supplies only the
  predictive frequency likelihood. Reverse direction is refitted independently.
- Baseline candidate posterior is `0.5 q_frequency + 0.5 uniform`.
  RX candidate posterior is `0.5 q_frequency+RX + 0.5 uniform`.
  Both use the same shortlist and the same support-preserving regularization.
  Identity is shared across each held block, not redrawn per observation.
- Normal/reversed/null reception use the same coefficients and data; only the
  direction feature changes. Shared detection/ratio effects remain integrated.

This is not the same experiment as the earlier temporal replay or its posterior
blend. Grouping, per-partition identity/CFO fits, scored observations, and the
regularization comparison changed. The result must not be attributed to any
single one of those changes in isolation.

## Verification and limits

All six result files completed. An independent receipt checker reconstructs
posterior weights, predictive scores, and aggregates; verifies partition labels
and full observation accounting; checks null cancellation and quadrature
receipts; and rejects duplicate or missing reciprocal predictions. Source code
hashes and input/model digests accompany each shard. The local suite has
**23 passing tests**, including tests that changing held frequency values cannot
change training shortlist/CFO, and that corrupted scores/partitions are rejected.

The initial smoke invocation failed before producing a result because the public
track contract forbids an all-evaluation mask. The adapter was corrected to
extract the two complementary valid masks and combine their disjoint endpoints;
no public contract was changed. All six successful shards use the same corrected
runner. A toy test's hand-calculated expected probability was also corrected
from 0.34 to 0.38 before the successful cohort runs completed.

**This remains conditional development evidence.** RX coefficients, feature
scalers, and random-effect folds exclude the scored recording, but frequency
hyperparameters and pairing calibration include it. Tracks were constructed
using the full original recording. These six recordings and previous outcomes
have already informed model development. Ten-second grouping does not prove
all temporal dependence disappears, and excluded short tracks can differ from
the retained subset. The gain is modest, with real recording-level regressions.

## Decision toward the positioning goal

Unlike the preceding overconfidence replay, this comparison retains a positive
mean against an equally regularized geometry-free baseline and separates normal
from reversed orientation in the aggregate. That supports a **recording-disjoint
predictive test with frozen settings**, not model promotion. Use eligible
recordings outside calibration and prior development, choose membership from
metadata with a reproducible random seed, and bind the full training artifacts.
No evaluation recording may influence nuisance calibration or feature scaling.

If that test supports incremental RX benefit, proceed to matched geographic
searches with independent Sacramento/Reno candidates and compare paired distance
errors. The full goal—better geographic resolution—remains unproven until then.

## Reproduction

These runners require the original research receipts, readable cached inputs,
the local TLE archive, and the deployed analysis Python environment. They do not
collect radio data. Each output path refuses overwrite.

```bash
python run_grouped_rebuild.py --session-index 0  # indices 0 through 5
python verify_grouped_rebuild.py
python summarize_grouped_rebuild.py
python -m unittest discover -s . -p 'test_*.py'
```

`grouped-rebuild-summary.json` binds all six shards and contains exact values.
The source-level protocol remains in `RANDOMIZED_REBUILD_PROTOCOL.md`.
