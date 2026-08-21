# Alternate CFO line product

The production analysis graph now persists one bounded, candidate-only alternate CFO
line result for each receiver path. This is an additive research surface. It does not
feed CFO correction, final detection, attribution, or Standard trajectory selection.

## Algorithm choice

The producer uses the weighted alias-aware Hough implementation described and measured
in [`reports/2026_08_20_line_finder.md`](../../reports/2026_08_20_line_finder.md).
On the persisted 5d4d RX1 study it recovered the same relevant real tracks as robust
RANSAC in about 0.133 seconds instead of about 7.16 seconds; the time-ordered DP variant
took about 60.46 seconds. Hough therefore provides the best measured bounded production
candidate for this non-authoritative surface.

## Graph and products

Each `path-alternate-tracks` CPU job has `IqAccess.NONE`, depends on the exact
`path-standard` node for the same receiver path, and consumes only its persisted
`standard.pilot-scan/v3` product. It publishes exactly:

- `standard.alternate-cfo-track-bank/v1` (`application/json`, scientific); and
- `standard.alternate-cfo-tracks-png/v1` (`image/png`, presentation).

For the normal two-radio/four-path recording this changes the sealed graph from 8 jobs,
10 edges, and 98 products to 12 jobs, 14 edges, and 106 products. Radio and paired
scientific reducers still depend on `path-standard`, not the alternate candidate node.

The JSON carries the exact pilot content digest, the complete effective configuration
and its canonical digest, source/detected/returned/truncated counts, and at most eight
published tracks. Detection is capped at sixteen tracks and 25,000 input points. Each
track records support, weighted support, span, slope, zero acceleration, intercept
modulo the 227.272 kHz alias spacing, circular residuals, maximum temporal gap, a
deterministic geometry confidence class, and `research_only` status. The strict codec
rejects unknown keys, non-finite values, inconsistent counts, digest drift, and breached
bounds.

## Presentation and failure behavior

The recording detail Standard-analysis section presents the alternate rows in a separate
table and serves the already-persisted PNG at the closed `cfo-alternate` artifact name.
Receiver-path tabs show their exact PNG; combined tabs aggregate bounded JSON rows but do
not invent a paired image. Missing products produce an explicit absence state. Duplicate,
corrupt, wrong-scope, digest-mismatched, or oversized artifacts fail closed.

The PNG renderer has fixed dimensions, DPI, labels, colors, axes derived from the complete
bounded persisted evidence, explicit software metadata, and a render lock. It draws every
visible alias lift of each canonical line and is byte-deterministic for identical inputs.
