# DS11 exact-IID full-catalogue numerator pilot

This prospective pilot asks whether the frozen DS11 shortlist omits material
training likelihood under the original independent Student-t4, 100 Hz model.
It is a numerator audit, not a position fit and not a calibrated identity
posterior.  The full-catalogue divisor remains unchanged.

Freeze original-plan indices 0 and 1.  Index 0 is the first original scan.
Index 1 is the scan with the lowest already-exported, training-only
`minimum_anchor_top8_mass` among the original 32 scans
(`0.9233187825367867`).  Within each scan select the first three bank-eligible
track IDs in lexicographic order.  No held observation, reference coordinate,
geographic error, or result of this audit selects a scan, track, or setting.

Evaluate two settings per selected track: configured center `(0, 0, 0)` and
the scan's saved, qualified original-IID endpoint.  This is 6 settings per scan
and 12 total.  Reconstruct the exact causal catalogue declared by the bank:
start with its baseline NORAD order, select the newest element epoch for each
NORAD across its bound provider snapshots, and apply the same labelled-debris
exclusion.  Access snapshots only through the read-only `TleArchiveReader`.

For an off-grid endpoint timing, propagate the full catalogue at the same two
quarter-second nodes bracketing the timing and linearly interpolate position
and velocity before computing Doppler.  This deliberately reproduces the
frozen baseline prediction path; direct propagation at the fitted timing would
be a different model.  Require retained predictions to replay the bank within
`1e-6` Hz and retained visibility masks to agree exactly.

Profile one CFO per candidate from training observations only with the actual
batched multi-root profiler in `tools/ds7_fast_baseline_adapter.py`, including
the frozen 1 MHz Gaussian CFO penalty.  Compare `logsumexp` of training scores
over all visible causal candidates with the same quantity over retained visible
candidates.  Report retained numerator mass, omitted numerator mass in log
space, the leading physical NORAD and whether it is retained.  Do not use held
values in any score.

Run one process per index, sequentially, with one BLAS thread and a 90-second
cap per process.  Persist every track/setting case immediately and preserve all
terminal receipts and partial outputs.  Do not expand the location grid, scan
panel, or track sample before review of this pilot.  No RF, IQ, reference error,
position optimization, archive mutation, or QNAP mutation is permitted.

