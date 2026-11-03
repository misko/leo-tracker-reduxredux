# DS13 multi-target activity-persistence prototype

This report-local prototype jointly assigns positive GLRT peaks to concurrently
active satellites with exclusive row/target matching and an elapsed-time-aware
factorial activity transition. `assignments.csv` is the persistent-model hard
assignment; `assignments-persistence-disabled.csv` contains the complete matched
control assignment, and `receipt.json` records both summaries.

Run with:

```bash
.venv/bin/python reports/2026_10_03_ds13_multitarget/activity/run_activity.py
```

Use `--output-dir` to preserve a separate run. The `rf-fitted-c/` and
`rf-zero-c/` directories are matched fixed-position RF arms; they measure
frequency-fit/activity effects, not position accuracy.

The source archive is positive-only. Consequently this is explicitly a
conditional positive-group diagnostic: missing archive rows are not fabricated
as observation opportunities. See the receipt for the evidence heuristic,
bounded-approximation details, tests, and scientific limitations.
