# Scoring and cache-loading performance experiments

Loading the compressed state arrays once per scan avoids repeatedly decompressing
the entire NPZ array for every track. On the first frozen TRAIN scan, all 93
prepared tracks, metadata, masks, interpolated states and candidate IDs were
**exactly equal** to the baseline loader. Complete preparation took **3.171 s
before and 0.092 s after**, a 34.4x speed ratio in this small benchmark.

This accelerates cache loading, not geographic likelihood evaluation. No model
or inference result changes. `loader.py` implements the change and
`benchmark_loader.py` verifies equality; `loader_results.json` binds the inputs
and sources. Both load timings use the same existing on-disk first-TRAIN cache;
this is not an end-to-end eight-hour fitting speed claim.

## Packed scoring did not help

This experiment concatenates track observations and profiles candidate CFOs in
candidate blocks, replacing per-track Python loops with NumPy reductions. It
preserves the frozen scalar model's visibility rule, duration weighting,
800 Hz cap and first-candidate tie rule. It does not change production code.

At six predeclared prior-centre/offset points using the first frozen TRAIN scan,
all candidate assignments agreed and the score/offset checks passed at 1e-6 Hz
or tighter. Synthetic tests also cover different candidate block sizes and
invariance to reserved-frequency changes.

However, the benchmark took **0.429 s packed versus 0.327 s scalar**: about 31%
slower, or a 0.76x speed ratio. This is a small single-scan benchmark, not a
general throughput guarantee, but it supplies no reason to adopt the change.
Keep the existing scalar implementation for the current numerical studies.

Reproduce from the repository root:

```bash
.venv/bin/python reports/2026_09_23_long_training_fast_score/benchmark.py
.venv/bin/python reports/2026_09_23_long_training_fast_score/benchmark_loader.py
```

`results.json` records the six sites, assignment equivalence, numerical deltas,
timings, and input/source hashes. No reference coordinate, validation/test data,
position optimization, or new recording is used.

The exact benchmark/scorer sources bound by the recorded outputs are preserved
in `*_as_executed.txt`. Their `.py` versions were subsequently formatted without
changing their Python ASTs. `source_formatting.json` maps both versions and their
hashes; the loader itself is unchanged. Timings were not regenerated for style
changes.
