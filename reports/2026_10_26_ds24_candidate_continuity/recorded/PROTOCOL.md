# Frozen recorded-export persistence rule

This is an RF-only diagnostic on the complete existing DS24-0011 tracking
export: all 3,754 original winners, 117 original graph owners, every exported
candidate and every gate-passing deduplicated candidate. No detector/IQ,
catalogue, identity, GPS, position, graph reassignment, or source trimming.
Candidate hypotheses in a receiver window are correlated alternatives, not
new independent observations. Original graph ownership and quality flags
remain provenance rather than acceptance of a new path.

The acquisition start is valid_start_counter plus the integral sample offset
from probe_start_ms. Relative to the original clock-anchor sample counter,
global frame phase is (((start-origin)*750) % integer_fs)/750 plus the
candidate integer epoch and fractional epoch offset, modulo exact fs/750.
Reduce the integer remainder before adding fractional values. Never use
payload packing indices, visit indices, midpoint counters, rounded frame
periods, or local epochs alone. Preserve raw counters. Receiver identity is
native receiver 0/1 mapped to RX1/RX2. Acquired CFO is unavailable in this
export and stays null. No UTC claim is needed for relative counter phase.

Deduplication uses the unchanged ds23_frame_registration.unique_peaks:
gate-passing candidates sorted by decreasing margin, suppressing pairs with
circular epoch distance <fs*120ns AND circular CFO distance <250Hz. The CFO
alias period is 1/4.4 microseconds. All rejected/duplicate candidate rows remain
in a separate full ledger. Original winners are maximum margin, lower-rank
tie break, exactly reconciled to all native observation IDs.

Pointwise nearby alternatives use the PREVIOUS inventory's rule unchanged:
circular epoch distance from the original winner <=3 samples, and circular
CFO distance in (250,5000] Hz. This is a proposal, not evidence of two sources.

For persistence, use only those nearby alternative rows within each original
owner. Enumerate all distinct-time seed pairs separated by [0.25,5] seconds;
initial circular CFO slope <=5000Hz/s and global-frame-phase slope
<=300samples/s in absolute value. A paired linear model admits rows within
250Hz and 3 samples, respectively, with at most one candidate per original
receiver window (lowest normalized squared residual, then higher margin,
lower rank, candidate ID). Perform exactly two linear refit/reselection
passes. Split selected rows at gaps >2 seconds, then require >=5 windows and
>=3 seconds of support; refit each run once and recheck the original rate and
maximum residual limits. Choose the largest path, then longest span, lower
CFO squared error, lower epoch squared error, and lexicographic candidate IDs.
These fixed broad drift bounds are engineering sensitivity limits, not
calibrated physical likelihoods or satellite-specific constraints.

Select at most one positive original owner by chronological owner start,
then receiver, channel and owner key. Select one unflagged control by the same
order from owners with >=5 original points, >=3 seconds span, no gap >2 seconds,
and zero pointwise nearby flags. Do not replace or loosen criteria if absent.
Expose ALL complete candidate windows for each selected owner to the separate
prototype, not only path inliers. Full denominators and failures remain public.

Pure counter/alias, known-path, permutation, duplicate-window and drift/gap
tests plus an actual first-window native identity/schema smoke precede source
freeze and independent preflight. One run only after B PASS; <=180 cumulative
numerical worker-seconds, one numerical worker and BLAS thread. Charge prior
metadata reads as one second and the preserved failed first-window identity
adapter assertion as a further conservative one second. Native observation
IDs remain the authoritative historical IDs; newly computed research window
IDs are separate identifiers, reconciled by exact receiver/channel/time,
winner CFO and margin. No recorded path outcomes have
been computed when this rule is frozen. Persisted alternatives could be
correlated detector refinements or interference; continuity alone cannot
establish a second physical source or usable localization information.
