# Full 8-hour frozen TRAIN position baseline

This is the fixed tau-zero, altitude-zero, two-prior baseline over all 72
sessions in the frozen `2026-09-21T00:00:00+00:00` TRAIN group. The group was
selected by that inventory label before cache export. It contains 3,587
eligible 3-second tracks and 97,993 eligible observations; all 72 receipts
and compact causal state caches verified against the sealed inference bindings.

The summed capture duration is 21,604.615 s (6.00 h), while the first-to-last
capture span is 28,740.862 s (7.98 h); the largest inter-start gap is
1,152.600 s. These are repeated short captures across an 8-hour block, not a
continuous 8-hour observation.

The search uses Sacramento's 250 km and Reno's 500 km prior disks, grid spacing
100 km down to 0.1953125 km, and a spacing-diverse beam of three retained cells.
Every tested location scores the retained causal candidate pool and profiles
each track's identity and constant frequency offset using training rows only.
Loss is duration-weighted track RMS capped at 800 Hz; tracks shorter than 3 s
are excluded by the fixed policy. This is a coarse-to-fine heuristic, not an
exhaustive fine grid or a certified global optimum. Only location is shared
between tracks in this baseline; timing corrections remain zero.

| Prior | TRAIN duration-RMS (Hz) | Held capped / uncapped RMS (Hz) | Post-seal reference distance (km) |
| --- | ---: | ---: | ---: |
| Sacramento | 295.369 | 311.967 / 392.823 | 7.548 |
| Reno | 295.374 | 311.986 / 392.813 | 7.651 |

`results/inference.json` and its `inference.sha256` were written before any
complementary-row score or reference-distance calculation. The inference used
only training masks, no position truth, validation, or test sessions. The
later `results/results.json` adds fixed-point held scores and the post-seal
reference diagnostic; its digest is in `accounting.json` and
`results/results.sha256`.

The selected basins are close for the two frozen priors: Sacramento
`(37.8473988, -122.3997167)` and Reno `(37.8477882, -122.3985273)`. Their
reference distances remain kilometres, so this baseline does not demonstrate
the sub-300 m target. `nested_duration_error.png` compares the post-seal
reference diagnostic for the nested 1/6/16/72-scan runs; it is descriptive and
does not select a model or a location.

The executed `search.py` source is bound in `inference.json` as
`sha256:617ec616fe13f65e6f8f317b6bf2a2d7bcc9ea72f2146d39c86e52b11235ac74`.
It loaded each session through the verified fast loader once and recorded
6.767 s preparation plus 1,897.585 s search time (1,904.352 s total). Do not
replace it when reproducing the seal.

Reproduce the numerical run with a fresh output directory:

```bash
.venv/bin/python reports/2026_09_23_long_training_full8h_position/search.py \
  --manifest reports/2026_09_23_long_training_cache_full8h/manifest.json \
  --cache-root /tmp/leo-long-training-cache-full8h \
  --single-tool reports/2026_09_23_long_training_search/search.py \
  --fast-loader reports/2026_09_23_long_training_fast_score/loader.py \
  --output /tmp/long-training-full8h-reproduction
```

Verify this result and regenerate the accounting record with:

```bash
.venv/bin/python reports/2026_09_23_long_training_full8h_position/check_results.py \
  --manifest reports/2026_09_23_long_training_cache_full8h/manifest.json \
  --cache-root /tmp/leo-long-training-cache-full8h \
  --qualification reports/2026_09_23_long_block_full_qualification/results.json \
  --results reports/2026_09_23_long_training_full8h_position/results \
  --search reports/2026_09_23_long_training_full8h_position/search.py \
  --single-tool reports/2026_09_23_long_training_search/search.py \
  --fast-loader reports/2026_09_23_long_training_fast_score/loader.py \
  --output reports/2026_09_23_long_training_full8h_position/accounting.json
```

The verifier fail-closes on a manifest/session/cache/source hash mismatch, an
inference seal mismatch, incomplete qualification, non-TRAIN inference,
changed sealed selections, or missing held scan coverage. It passed for this
report, and Ruff passed for the verifier and plotting helper.
