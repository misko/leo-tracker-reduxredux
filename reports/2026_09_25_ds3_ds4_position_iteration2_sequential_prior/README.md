# DS3-to-DS4 sequential position prior

This experiment freezes a receiver-position prior using DS3 only, then updates it
causally with DS4 scans. It consumes the sealed, truth-blind per-scan Sacramento
position estimates from iteration 1.

The DS3 prior retains the 75% of scans with the lowest RF residual RMS, a rule fixed
in iteration 1. Each retained scan contributes one unit-vector vote. Every new DS4
scan contributes one additional vote. No surveyed coordinate, horizontal error, or
post-seal result is available to `infer`.

Two DS4 views are reported:

- each chronological group of eight combined independently with the frozen DS3 prior;
- a causal cumulative estimate after each new group of eight.

This is an online historical-prior method. Its group-of-eight results must not be
described as eight-scan-only estimates because they include the frozen 42-scan DS3
prior.

Reproduce:

```bash
.venv/bin/python reports/2026_09_25_ds3_ds4_position_iteration2_sequential_prior/run.py infer
.venv/bin/python reports/2026_09_25_ds3_ds4_position_iteration2_sequential_prior/run.py postseal
.venv/bin/pytest -q reports/2026_09_25_ds3_ds4_position_iteration2_sequential_prior/test_run.py
```
