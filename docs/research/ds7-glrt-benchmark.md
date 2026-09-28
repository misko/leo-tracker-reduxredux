# DS7 GLRT speed benchmark

The [measured report](../../reports/2026_09_28_ds7_glrt_benchmark/REPORT.md) compares original GLRT, exact optimizations, two-candidate search, causal prior-CFO search with fallback, and exact four-worker analysis on the same saved DS7 IQ.

The frozen development cohort covers 2.5, 5, 7.5 and 10 MS/s. Two chronological repeats provide 280 completed method evaluations. Exact methods preserve all scientific outputs; approximate methods preserve every reference confirmation in this small cohort but lose alternative positive hypotheses. The report separates elapsed latency, aggregate CPU cost, exact equality, hypothesis recovery, and confirmed-detection recovery.

At 2.5 MS/s, exact serial optimization reduces CPU by 5.1%. Two-candidate search reduces CPU by 34.5%, retaining 62.8% of positive hypotheses and 32/32 confirmations. Four workers reduce elapsed latency by 3.56× with exact outputs but slightly increase aggregate CPU. These are server measurements, not ARM capacity estimates.

The [protocol](../../reports/2026_09_28_ds7_glrt_benchmark/SPEC.md), [scoring contract](../../reports/2026_09_28_ds7_glrt_benchmark/SCORING.md), [audit](../../reports/2026_09_28_ds7_glrt_benchmark/AUDIT.md), and [machine-readable results](../../reports/2026_09_28_ds7_glrt_benchmark/summary.json) retain the assumptions and receipts. Reproduction commands appear in the report. No RF collection or production deployment was performed.
