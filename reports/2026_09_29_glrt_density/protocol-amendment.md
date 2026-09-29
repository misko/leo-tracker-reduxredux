# Budget amendment, before comparing dense outcomes

The first visit required 5.76 seconds wall time / 5.58 CPU seconds. Restrict the
initial complete operational and held-out pilot to visits fully contained in
device time [0,30] seconds, preserving their original frozen partition. This
chronological restriction is based solely on compute cost, not signal quality.
The original 60-second specification remains as an audit record.

Run at most two workers. Reuse start-of-visit production windows only after
numeric equivalence checks. Derive the 20 ms control from even-numbered dense
windows after checking fresh 20 ms replay equivalence. Full replay results are
used for operational tracking; training-only results are used for held-out fits.

The unchanged production projector rejects overlapping windows. Therefore the
10 ms and 20 ms arms are expected to have identical scientific trajectory inputs
after that selection, with differing provenance identifiers. Do not alter this
selection to manufacture a density gain.

Reference quality rule: keep start-of-visit candidates passing the fixed 0.025
fractional margin gate; cluster frequencies separated by at most 2500 Hz using
complete-link clustering within the canonical 227272.727 Hz interval; require
exactly one cluster per visit/RX, selecting its highest-margin candidate. Reject
ambiguous references without consulting any fitted trajectory. Alias-conditional
comparison only: canonical branch is fixed, no test-time wrapping/refitting.

Match tracklets only within channel/edge/RX/RF lane, with at least four seconds
of overlapping training span and maximum predicted difference 2500 Hz at the
overlap endpoints after a training-only constant integer-alias alignment. Accept
only mutually unique compatible matches; keep all other cases in the ledger.
Assign a reference to a matched track only when exactly one baseline training
track spans its time on that lane. No reference frequency is used for assignment.

This pilot measures TLE-blind frequency track prediction. Catalogue matching and
TLE-based Doppler RMS are deferred; no claim of satellite or absolute Doppler
accuracy follows. Full 60-second and multi-recording confirmation are deferred.
