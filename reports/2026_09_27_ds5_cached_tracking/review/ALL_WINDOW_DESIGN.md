# Independent all-window development evidence

Before executing this diagnostic, fix membership to every receiver of every
new-development case in `new_data/cases.json`. Run the unchanged packed FP64
V4 detector, unseeded, maximum six confirmations. Require its first candidate
to equal the frozen independent reference in `new_data_v6.json` on every row.
Keep all candidates, including negatives and unsupported fits, with no
outcome-based selection. Verify dataset, IQ, binary and source hashes before
and after execution. No holdout or new RF data is used.

This is a post-outcome development diagnostic, not physical ground truth or a
replacement qualification gate. It may explain whether a cached positive
matches another independently positive window within the original 2 us/8 kHz
bounds. Absence from this finite candidate set does not prove a false alarm.
Neither this receipt nor any current/future reference enters strategy state.
Do not count diagnostic timings as performance or multiply them into speedups.
