# Exact R01 expansion handoff

panel.json.slots[*] retains the source-reader interface: request_id/case,
probe_metadata and probe (visit, native origin/duration), tracking.path/hash,
source_input.path/hash, raw_authority with exact inventory/manifest/index/IQ
digest, sample_rate_hz and both cells. No target candidate values are included.
block_ids bind every target to RF-only nomination; duplicate paired windows
are merged after per-block caps. Stable native_observation_id is the validator's
unchanged observation-ID mapping, enabling cross-panel deduplication.

prediction_packets.json uses the exact R01 enriched schema. rows[*].header has
native integer generation and distinct stream_generation; target_support and
each mode donor's support bind native start/stop/generation/IQ/index digests.
Mode hypotheses/ranks/timing/CFO/rates/widths come from exact R01 predictor.
Use the unchanged R01 timing adapter, not R02 midpoint/curvature controls.
Frame partitions remain stable raw owner-derived. Prior recovered owners are
not extra independent observations and newly recovered values never become
donors. Only original tracking candidates supply causal histories.

Missing metadata/no donor/failed rows remain. A packet must have verified native
metadata before reading IQ. The timing owner exhausts public FastSegmentSource
and verifies exact IQ/target/acquisition against raw_authority. This package has
not read IQ and has not established fresh paired detector parity at new windows;
label reused R01 runtime/detector evidence as reuse. No scoring is authorized or
performed by this prediction stage. Root binds dependent raw execution.
