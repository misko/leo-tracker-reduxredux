# Paired opportunity audit

## Finding

The ten immutable roof caches support a complete **receiver-window** export,
including an observed no-candidate outcome.  They do not support a complete
**target-window** sequence.  A window with no passing candidates has no
candidate or satellite identity, and first/last target detection cannot be
identified without forecasting a named target into that window.

The prepared exporter is `tools/rx_paired_opportunities.py`.  It uses only
public `TrackingInput`, `TrackingProbe`, `TrackingCandidate`, and timing
fields.  It must run under the production interpreter that owns that pickle
contract.  No cache was exported during this audit.

Each JSONL opportunity has exactly two receiver views when the cache is
complete.  It records `observed_candidate_present`,
`observed_candidate_absent`, `missing_receiver_probe`,
`duplicate_receiver_probe`, and qualification failures separately.  Candidate
records remain nested in their source window and carry the existing stable
`anchor_key`:

`session_id:visit_index:probe_index:receiver_id:candidate_rank`.

The exporter obtains `projected_candidate_id` and its public source interval
from `project_scanner_candidates`; raw candidates without a projection carry a
null projected ID.  Those fields permit the existing source-link/projected-
observation join.  They are not satellite IDs; `satellite_id` is null in every
exported row.

## Timing and bindings

Window timing is counter-anchored rather than inferred from row order.  The
start is `first_sample_estimate_utc_ns + round((valid_start_counter -
session_start_device_sample_counter + probe_start_ms * sample_rate_hz //
1000) * 1e9 / sample_rate_hz)`.  The end adds `probe_ms * sample_rate_hz //
1000` samples.  The source binding JSONL retains both endpoints, the raw
counter values, cache digest, session/visit/probe/lane fields, and receiver.

The inventory already establishes 22,155 complete visits and 44,310
simultaneous receiver probes.  It declares 20 ms support at offset zero.  The
export additionally verifies each cache SHA-256 and requires raw session,
input-manifest, and analysis-manifest identities to equal its inventory entry.

## Available outcome balance

The existing fixed compatibility accounting shows the following raw paired
window categories across the ten sessions: 8,929 both-compatible, 4,316
RX0-only, 542 RX1-only, 5,600 neither, and 2,768 both-unmatched.  These counts
are useful only as receiver-window accounting.  RX-only is conditional on an
anchor candidate; neither and both-unmatched have no candidate identity.

The chronological six-calibration/four-holdout cohort spans 10, 7.5, and 2.5
MS/s in calibration; 5 MS/s occurs only in holdout.  A category-balanced
whole-recording 6/4 split can keep the singleton 7.5 MS/s recording in
training while covering every evaluated rate (10, 5, and 2.5 MS/s) in training.
It cannot place every rate in both arms, which is unnecessary for the support
requirement that each evaluated rate be represented in training.

## Candidate prediction and sequence feasibility

The compact associated product has 25,323 projected observations and 10,369
held detection-selected anchors.  Its per-track candidate IDs and weights are
frozen from the old within-track frequency mask, and its join to held anchor
rows is exact.  This supplies candidate-specific LOS at detected anchors, not
candidate predictions at every raw window.  It also predates a prospective
whole-record split.

Consequently the next defensible step is to freeze the paired-opportunity
export, then use its anchor keys to attach the already materialized projected
IDs where available.  A new target-level sequence requires a separate,
training-only candidate forecasting/association artifact that establishes
target visibility and opportunity eligibility before reading held receiver
outcomes, and keeps an entire source-overlap group in one split.  Until then,
first/last order and neither are unavailable rather than negative detections.
