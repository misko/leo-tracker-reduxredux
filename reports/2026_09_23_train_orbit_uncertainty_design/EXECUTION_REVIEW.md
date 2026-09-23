# Independent pre-result execution review

Reviewed the live pilot source at SHA-256
`8b1ce03622b62231a26bd92e2a3c1adfe84fdf91bd7cf237cbcce21be781cde7`
and test source
`c61f412a725cbf57d7269827c6db6bcef933d774b435403b7bcf9dc8b1996dd1`
while its authorized execution was live. No source was modified and no outcome
or reference-coordinate result was inspected.

The source now obtains all four arms from `view_inputs.load_view_arms()`: first
and second TRAIN six-session prefixes, each with its own Sacramento and Reno
tau-zero baseline coordinate, cache root, and training-only reconstructed fixed
IDs. It no longer reuses the full-eight-hour Sacramento scale-5 identities or
a `[0, 0]` start. The helper verifies sealed baseline/source/cache/manifest
bindings and excludes VAL and TEST.

For each selected candidate, the source reads the session's exact strict-metadata
causal snapshot and parses that candidate's element epoch from that snapshot.
It does not reuse the old full-view epoch row for a changed first-six/Reno
identity. History is filtered in `target_point_phase` by each track's cutoff,
for both element epoch and first archive collection time. Duplicate TLE text is
retained at its earliest collection time rather than relying on archive order.

The separately saved public-port audit
`cutoff_receipts.json` binds exact `first_sample_estimate_utc_ns` values for all
12 sessions and verifies every receipt/metadata observation-ID order. It finds
all 774 track anchors equal the original first-sample estimate exactly (maximum
zero nanoseconds), with zero relative-time deviation. Therefore the pilot's
`anchor - 505 s` cutoff is numerically identical to the original strict causal
selection cutoff for every used source, and all bound snapshots are strictly
earlier. This is a transparent post-run verification; the live code itself does
not reopen public input receipts for that comparison.

The Doppler prediction preserves the existing `measured_hz` versus fixed
11.2 GHz reference-RF convention. It keeps `clock_s=0`; orbit-time phase shifts
are passed to propagation while Earth rotation remains evaluated at receive
time. Constant CFOs are projected by unique track segment using training rows
only. The objective consumes only training residuals, and the 1 MHz held-row
perturbation repeats each fit to test location/rate invariance. Exact final SGP4
states at the fitted phase are profiled with the same training-only CFO rule and
compared with the quadratic state approximation.

`ruff check` passed for the pilot and adapters. The pilot test and input-adapter
test passed (three tests). The unit coverage exercises disk containment and
post-cutoff history exclusion; the stronger receipt/timestamp evidence is in
the saved 12-session audit. Source review finds no remaining scientific blocker
to inspecting the completed numerical result. Result review must still check
convergence, active rate bounds, held perturbation invariance, and exact-state
differences before any post-seal geographic evaluation.
