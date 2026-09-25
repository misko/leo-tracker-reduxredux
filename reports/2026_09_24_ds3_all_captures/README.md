# DS3 all qualified captures — 2026-09-24 UTC

The frozen DS3 admission contains **56** qualified, terminal-complete
`scan-fw` captures from 00:00:02.155440Z through 22:20:02.797011Z. The audit
was observed at 22:36:58Z; the 22:30 scan is outside the declared capture
cutoff. All 56 recordings are included for raw-capture admission. This is an
inventory whose derived inference manifest now binds completed causal tracking
products for every admitted capture.

DS2-22 is a strict subset: all 22 DS2 sessions occur in this freeze, while 34
new sessions were materialized through fresh read-only analysis. The raw
admission manifest preserves the original DS2 receipt distinction. A stricter
capture-time audit subsequently admitted five conditional explicit LT3D
bindings in `inference-manifest.json`; the other 51 sessions may not inherit
geometry from radio identity.

The machine-readable [manifest.json](manifest.json) records raw capture paths,
schemas, UTC timing qualification, receivers/layout, dwell observations,
recording status, V14-evidence availability, geometry status, and explicit
exclusions. It was built read-only from `/srv/bulk/leo/scanner-adaptive-recordings`.

For leakage control, group all data from one `session_id` together, stratify
the deterministic whole-session split by radio, sample rate, and DS2 membership,
and record its seed before inference. Fit preprocessing only on training
groups. Reference coordinates are forbidden during inference and allowed only
for a separately sealed post-seal evaluation.
