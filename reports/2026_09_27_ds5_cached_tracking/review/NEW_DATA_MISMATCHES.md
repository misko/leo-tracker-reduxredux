# New-data cached mismatch diagnostic

This is a post-outcome diagnostic on the same nine development receiver-visits
that failed the 2 microsecond/8 kHz association in both `new_data_v6.json` and
`new_data_partial2.json`. Selection used those outcomes, so this is neither a
qualification result nor fresh validation. No held-out IQ was opened, no
threshold was changed, and no result was fed back into tracker state.

The diagnostic ran the frozen packed `NativeDwell` baseline with
`maximum=6, seeded=False` on the original full 120 ms receiver IQ. This performs
an independent acquisition and fractional confirmation for every ranked 20 ms
window. The binary SHA-256 was
`8cdc21362e8cb98a21550b0ba2024674881ca106706d9c799b33e5d4f5a7e614`,
identical to the v6 replay baseline. Its frozen build receipt SHA-256 was
`5103c6ebfde2a95e0ecdeec3c2e5c5c3253cf04aaca15da2fda1b5b6c0d1ee3e`.
The rerun required its top result to equal the original replay reference exactly
before examining lower ranks.

## Result

Seven of nine cached trajectories have at least one positive freshly fitted
all-window candidate within 2 microseconds and 8 kHz. Each such candidate is
below rank one. The blind top result and cached result therefore describe two
different positive trajectories in the same dwell; these seven mismatches are
best described as top-rank trajectory replacement, rather than loss of the
cached trajectory.

| Visit | Rate | RX | First matching rank | Timing error | CFO error |
|---:|---:|---:|---:|---:|---:|
| 1134 | 2.5 MS/s | 0 | 2 | 1.058 us | 8.9 Hz |
| 1136 | 2.5 MS/s | 0 | 5 | 1.988 us | 591.0 Hz |
| 1117 | 5 MS/s | 1 | 2 | 0.064 us | 149.1 Hz |
| 1118 | 5 MS/s | 1 | 2 | 0.003 us | 277.4 Hz |
| 1135 | 5 MS/s | 1 | 4 | 0.010 us | 22.8 Hz |
| 1137 | 5 MS/s | 1 | 3 | 0.304 us | 195.7 Hz |
| 1138 | 5 MS/s | 1 | 3 | 0.494 us | 286.1 Hz |

The v6 and partial-two-frame cached observations associate with each other in
all nine visits. Both variants obtain the same seven-of-nine fitted
corroboration result.

Visits 1122 and 1124, both 5 MS/s channel 2 RX1, have no all-window candidate
near the cached trajectory. Their cached observations are around -42 to -43 kHz.
All six fresh fits in each dwell converge around +108 to +110 kHz, with roughly
151 kHz CFO separation and 351 to 354 microseconds circular timing separation.
This is evidence that the two cached positives lack independent blind-fit
corroboration. It is consistent with a cached false acceptance, but it cannot
distinguish that from the blind search repeatedly missing a weaker overlapping
trajectory while locking to the dominant one. The corpus has unknown truth, so
these two observations must not be relabeled as false positives.

The complete machine-readable candidates, margins, comparisons, hashes, and
diagnostic native timings are in `new_data_mismatch_diagnostic.json` (SHA-256
`a10c390ce31dd59f2d711dc83009196d990dc1d096c5d279c71ff3967cf71a55`).
Those timings come from an outcome-selected nine-case rerun and are not valid
for a performance claim. The runner is
`review/run_new_data_mismatch_diagnostic.py` (SHA-256
`caeef8ce636b101a1eadbfc2e76653528854e2d2e87caa312fbf977aef4156ee`).
Its focused selection and cross-window matching tests pass.

