# Streaming tracker comparison protocol

Three independent first implementations: rolling weighted linear state (8 s
primary; 4/12 s optional sensitivity), frequency/rate Kalman state, and local
linear tracklets linked in time. Each uses the same frozen GLRT inputs, exact
receiver/channel/edge/RF lanes, 11.2 GHz CFO normalization, and alias handling.
No server tracks or satellite identities are supplied to the algorithms.

Evaluate both ARM detections and server detections to separate detector losses
from tracker differences. Shared primary measurement is the previously frozen
80% source-coverage / 80% in-span-purity criterion with a 2500 Hz same-source
circular CFO gate. Preserve original 63-reference scores; separately exclude
user-approved reference 10 for the reviewed 62-reference agreement score.
Reference 35 remains a flagged purity-metric limitation, not a new exception.

Report output hypothesis count, one-to-one matching, represented reference
segments, misses, and input limitations. Existing two-curve synthetic truth
provides known-identity coverage/purity including clutter, curvature and gaps.
An equal causal 8 s linear prediction diagnostic measures fit quality, using
at least five prior observations spanning two seconds, gaps at most four
seconds, and circular CFO residuals. This does not establish identity and must
be interpreted with fragmentation/coverage counts.

Benchmark host reconstruction separately from process/parse/output overhead.
Measure physical PLUTO+ reconstruction with bounded saved-data replay and
verify outputs against host. Target three ARM-input repeats; one server-input
run per algorithm to distinguish input effects. No RF collection, firmware
change, or production activation. Compare against prior verified server
lane-reconstruction median 8.1112 s, clearly labeled prior host timing on
different hardware/language. Include full-process time separately.

Each component owns tests for relevant curvature, crossings, aliases, clutter,
gaps and source timing. Defaults are documented before target scoring. Test
failures may be fixed, but do not silently tune on target reference membership.
This is bounded research, not a claim of exclusive physical satellite tracks
or full adaptive pipeline real-time qualification.
