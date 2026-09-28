# Sparse and progressive GLRT searches

The [experiment report](../../reports/2026_09_28_ds7_glrt_progressive/REPORT.md) implements reduced-window searches, four/six-candidate full schedules, and a progressive search that expands each receiver independently until confirmation or exhaustion.

The [measured tables](../../reports/2026_09_28_ds7_glrt_progressive/RESULTS.md) separate CPU cost, elapsed time, confirmed-detection recovery, positive-hypothesis recovery, and exact output equality at 2.5, 5, 7.5, and 10 MS/s. The 90%/80% targets apply to original confirmed receiver/visit pairs. Sparse methods intentionally return less evidence and are not replacements for full downstream Doppler analysis without further validation.

Implementations and tests live beside the report. They process saved IQ only and leave production detector contracts unchanged. The protocol and reports disclose the exposed development cohort, the preserved interrupted first attempt, fresh baseline comparisons, and source/input receipts. See the report for reproduction commands.
