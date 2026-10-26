Completed exact R01 application, no IQ or scoring. Authoritative selection is
COHERENT_EXPANSION_PLAN.md, not the older validator proposal. RF-only preview
selects four blocks: DS24-0011 CH5/RX0 65windows and CH7/RX0 67; DS24-0097
CH6/RX1 64 and CH5/RX0 67. Total263paired windows/526receiver cells; no block
hits80cap. Estimated raw replay220–330s per case from existing throughput;
timing owner keeps580s caps. This branch only prepares metadata/forecasts.

Exact hashed imports will reuse R01 predictor, request helper, native owner-ID
mapper and handoff.enrich. New outputs retain same enriched packet schema with
native target/donor authority and block membership. Original acquisition
histories only; newly recovered ledger points never feed donor prediction.
R01 timing adapter/scorer, including its legacy midpoint advance, remain
unchanged in this application. R02 forecasts do not enter it.

V1 handoff is preserved but revoked: shared live donor aliases corrupted some
stream_generation labels. V2 reloads serialized predictions before exact R01
enrichment. `prediction_packets_v2.json` SHA256 is
3eb5bbf491eae2f1c2300961ef6f88d5406720f02db57f2c6b97a59fdd0a881e.
`forecast_seal_v2.json` and `verification_v2.json` bind the complete audit.
4,670 row differences are exclusively stream_generation labels; numerical
forecasts and native ownership are unchanged. All526 fresh/redaction forecasts,
263 target windows,72 donor windows and8 original-panel overlap cells pass.
Forecasts available290/no donor236. REPORT.md and INTERFACE_V2.md describe scope.
