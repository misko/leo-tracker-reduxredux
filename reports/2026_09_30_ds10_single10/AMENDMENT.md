# Adapter correction

The slope and curvature launches for the first three scans failed before constructing groups or fitting: saved track timestamps are lists, so boolean indexing requires an explicit NumPy conversion. Corrected that representation-only bug; no observations, population, thresholds, starts or model settings changed. Original source is retained as run_before_array_fix.py and original failed logs/receipts remain. Those six engineering failures may be rerun under the same per-attempt budget with separate retry receipts. Later launches use the corrected adapter.
