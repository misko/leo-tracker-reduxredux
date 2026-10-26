Use `prediction_packets_v2.json` and `forecast_seal_v2.json`. Preserve the
original interface, scorer and numerical R01 forecast exactly. V1 remains an
audit artifact and is superseded for execution.

V2 reloads `predictions.json` before the existing `handoff.enrich`, preserving
the original JSON object boundary. The only row differences from v1 are
`stream_generation` label corrections; integer native `generation`, source
ownership, epochs, rates, uncertainties and CFOs are identical. Full diff:
`metadata_diff_v2.json`; full audit: `verification_v2.json`. Top-level added
provenance fields bind v1 and the correction protocol. This is a metadata
repair, not a prediction or scoring revision.
