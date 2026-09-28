# DS7 Wave 2 CFO matched-window experiment

> **Superseded interpretation:** see `CORRECTION.md` and
> `profile-results-v3.json`. The original `results-*.json` method labels do not
> represent three independent waveform estimators, and their held RMS values
> measure temporal self-consistency rather than frequency accuracy.
> `LANE-CORRECTION.md` further supersedes the four-window aggregation because
> visit 12 is on a different RF channel.
> `FINAL-CFO-RECEIPT.md` is the final eligible-lane and negative-control receipt.

This reference-free experiment used frozen 10 MS/s session
`scan-fw-a40658642d9ade6a`. It accessed cached metadata through
`ScannerTrackingInputStore` and IQ through the public, read-only
`AdaptiveHopIqStore`. It did not read the DS7 pose, full manifest, reference
positions, or score outputs.

`read-spec-v2.json` freezes the earliest two eligible all-training visits and
the earliest two eligible all-held visits with support on both receivers. The
selected visits are 5 and 8 for training and 11 and 12 for held evaluation.
There is one acquisition-bound candidate per receiver and visit. Its candidate
ID deterministically binds the candidate rank, native integer and fractional
epoch, CFO alias basin, edge, source interval, UTC support, receiver, and visit.

The public reader returns complete visits, so each execution read 38,400,000
bytes rather than the 6,063,936 bytes occupied by the selected source ranges.
Three bounded executions used 115,200,000 bytes in total, below the frozen
512 MiB lease. The final execution took 7.50 seconds, below the 120 second
limit, with one process, one BLAS thread, and `nice -n 19`.

For each method and receiver, the two training values define a UTC-linear CFO
line. Held CFO values are only evaluated against that line; they are never used
to fit it. `baseline` uses the cached acquisition CFO. `ordinary_profile` uses
the arithmetic mean of supported known-pilot frame estimates,
`robust_profile` uses their median, and `differential_phase` uses the production
pilot phase-slope aggregate. All 32 method/window rows were supported.

Held RMS errors in Hz were:

| receiver | baseline | ordinary | robust | differential phase |
| --- | ---: | ---: | ---: | ---: |
| 0 | 395.968 | 317.563 | 313.684 | 313.684 |
| 1 | 246.141 | 189.318 | 193.926 | 193.926 |

The ordinary estimate had the lowest held RMS on receiver 1; robust and
differential phase had the lowest held RMS on receiver 0. Robust and
differential results coincide here because the production aggregate selects
the same median statistic on these supported frames. This is a small
candidate-conditioned measurement experiment: two training visits determine
each line exactly. It does not establish a calibrated population result or a
geographic improvement.

`read-spec.json` is the preserved, unexecuted all-training v1 design.
`results-v1.json` is retained as a rejected run because nearest-CFO recovery was
ambiguous when candidate ranks shared a CFO. `results-v2.json` is the corrected
pre-format replay. `results-final.json` is the sealed result from the final
source. No result was reference-scored.

## Reproducibility

- Freeze source SHA-256: `7c22a796a5d65b87240e2af4a524ff847ed6fb0400e24088eca766edb1b2b02c`
- Final runner SHA-256: `93e04b61d5722a3dc276d3d7cfac0fa41c09141ea0f055498e240a56ec98f26f`
- Spec v2 SHA-256: `435cce6d58a9e2f71c0a58ff07d1dd16d9fd5e570317b686b93ca89ec82ac59b`
- Final result SHA-256: `30155b33b77296fc331c672733e5369c31c779193a3a4e094054a5a4b55f2b31`
- Repository revision: `a887eec1560606dc7f4ffcbc5bbded1bd798f1c8`
- Runtime: Python 3.14.4, NumPy 2.4.6, SciPy 1.18.1
- Installed package root: `/opt/leo-tracker/current-api/.venv/lib/python3.14/site-packages/leo`

Final command:

```text
sudo -n timeout 118s nice -n 19 env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 /opt/leo-tracker/current-api/.venv/bin/python tools/ds7_cfo_wave2_run.py --spec reports/2026_09_27_ds7_wave2/cfo/read-spec-v2.json --output reports/2026_09_27_ds7_wave2/cfo/results-final.json
```

Component checks: Ruff passed; 2 tests passed.
