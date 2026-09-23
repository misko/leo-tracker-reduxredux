# Direct-SGP4 interpolation audit at sealed long-TRAIN selections

This audit checks the cached one-second state interpolation only at the sealed
TRAIN-only 6/16 selected coordinates and per-track candidate assignments from
`long_training_search_multi`. It verifies both seal hashes, preserves every
selected coordinate and training objective, verifies each cache/receipt hash,
and reads the exact saved causal snapshot instance recorded by each receipt.
No position search, reference coordinate, validation data, catalogue update, or
new cache export is used.

For each selected track, direct SGP4 and linearly interpolated ECEF state
predictions are converted to 11.2 GHz Doppler at the fixed selected coordinate.
The audit removes one mean interpolation-minus-direct Doppler constant on that
track's TRAIN rows, matching the fitted constant-CFO nuisance form, then reports
the residual shape RMS. This tests the numerical approximation, not the fit's
catalogue, identity, timing, receiver, or orbit-error assumptions.

| TRAIN view / prior | Matched tracks | Median shape RMS | Maximum shape RMS |
|---|---:|---:|---:|
| 6 / Sacramento | 476 | 0.028265 Hz | 0.064781 Hz |
| 6 / Reno | 476 | 0.028259 Hz | 0.064785 Hz |
| 16 / Sacramento | 1,130 | 0.027298 Hz | 0.073822 Hz |
| 16 / Reno | 1,130 | 0.027406 Hz | 0.073791 Hz |

Across the four sealed views there are 3,212 view-track comparisons (the nested
6/16 views intentionally repeat some tracks). The median is 0.027751 Hz and
the maximum is 0.073822 Hz. The worst 16-Sacramento track is
`scan-hop-15fa6063a0c92327` / candidate 63758, with 0.073822 Hz RMS and
0.098941 Hz maximum absolute residual after constant removal over three TRAIN
observations. All selected tracks matched a cache candidate and direct causal
propagation.

The result supports treating cache interpolation as small relative to the
hundreds-of-Hz residuals and kilometre-scale position discrepancy in this fixed
model. It does not establish sub-300 m positioning or calibrate the substantially
larger catalogue-update inconsistency observed in the separate causal-history
audit.

`audit_selected.py` is lint-clean and its SHA-256 binding is
`2ed978d968c5db9ce77a5e492c53a8342ccaaa8f37db3d6f3cc7f9892905eec5`.
`results.json` records every view's worst five tracks and bindings to the sealed
inference/results and public interpolation/benchmark helpers.

Reproduce from the repository root with the verified first-sixteen cache export:

```bash
sudo -n -u leo .venv/bin/python reports/2026_09_23_long_training_selected_interpolation_audit/audit_selected.py \
  --inference reports/2026_09_23_long_training_search_multi/results/inference.json \
  --inference-sha256 reports/2026_09_23_long_training_search_multi/results/inference.sha256 \
  --results reports/2026_09_23_long_training_search_multi/results/results.json \
  --results-sha256 reports/2026_09_23_long_training_search_multi/results/results.sha256 \
  --cache-root /tmp/leo-long-training-cache-first16 \
  --interpolation-helper reports/2026_09_23_long_cache_feasibility/helper/regular_cache.py \
  --benchmark-helper reports/2026_09_23_long_cache_feasibility/helper/benchmark_regular_cache.py \
  --output /tmp/long-training-selected-interpolation.json
```

An initial implementation was stopped after review found an aggregation-key
bug. Two subsequent input checks failed before producing results while resolving
snapshot digest formatting and repeated content at different collection times.
The completed receipt binds the corrected source and exact snapshot instances;
none of these failed attempts produced scientific outputs or changed selections.
