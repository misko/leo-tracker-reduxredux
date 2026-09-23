# Adaptive all-track position analysis

The standard adaptive tracking job publishes the additive
`scanner-adaptive-tle-position-v2` product after scanner analysis. Existing
assisted positioning and Denver-region products keep their own contracts.

This product reconstructs every eligible track with at least three seconds of
support and six observations. It searches separate Sacramento (250 km radius)
and Reno (500 km radius) priors at 100, 50, 25 and 12.5 km spacings with a budget of
400 evaluated positions per prior. It retains the best evaluated point across
all levels and reports the best finest-level point separately. An unfinished
frontier is explicitly reported; a completed artifact is not a globally
completed search or a position fix.

The score is the square root of the represented-second-weighted mean of capped
squared track residuals. Each track contributes at most 800 Hz squared; an
unmatched track receives that penalty. Time shift and frequency offset are
fitted on training observations separately for each candidate. Satellite
identity and position are selected using the fixed randomized evaluation RMS.
Consequently this RMS is a selection score, not independent test accuracy.
Counts below 200 Hz are supplementary diagnostics. The causal catalogue is
selected before the capture, without using the true receiver location.

## Outputs

The read-only API exposes the manifest and machine-readable document at:

`/api/v1/scanner/tracking/{session_id}/adaptive-tle-position-v2`

The manifest binds the map at
`/api/v1/scanner/tracking/{session_id}/adaptive-tle-position-v2/map.png?sha256=...`.
The web tracking panel displays the map, per-prior selected coordinates and
scores, track/observation counts, budget status, and a JSON download. Scientific
insufficiency is labeled with its reason; transport or processing failure must
not be reported as a successful numerical result.

The original v1 contract, namespace and `/adaptive-tle-position` routes remain
readable for the former 500 km / 500 km analysis. They are not substituted for
missing v2 results. The different prior radii require a new immutable publication
and configuration digest; old artifacts are never relabeled or overwritten.

The local immutable store owns its namespace beneath the configured bulk root.
QNAP is not a writable destination. New tracking jobs use the existing `memory`
resource class to bound simultaneous orbit-state banks; each job uses at most
four scoring processes sharing its bank.

## Replay and backfill

Use an exact qualified release and the existing recorded-data ports; no RF
collection is required. A single-session replay is available through:

```bash
python -m leo.cli.adaptive_tle_position \
  --bulk-root /srv/bulk/leo --tle-root /var/lib/leo/tle \
  --session-id SESSION_ID --workers 4
```

`--output-root` selects a separate local artifact root for a canary. To backfill
a bounded historical window through the standard processing queue, use:

```bash
python -m leo.cli.adaptive_processing_queue --bulk-root /srv/bulk/leo \
  backfill-tracking --since-utc-ns START_NS --until-utc-ns END_NS --limit COUNT
```

Run the queue producer and workers from the same qualified release. Freeze the
window membership before enqueueing, then verify every expected session through
the public store/API, including its PNG digest and decoded image. Report
scientific insufficiency, incomplete prerequisites, and execution failures
separately from diagnostic position results. Never infer completion merely
from a zero pending-job count.
