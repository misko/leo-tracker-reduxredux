# Position scanner v0.64 host entry point

Use the companion's new negotiated v6 mode together with the v0.64 kernel and
iiOD. The prerequisite rate-aware continuous recorder changes are ported onto
tracker main; published eight-target checkpoints and 2.5 MS/s IQ formats retain
their meanings. Position runs use a separate `position_scan_run` envelope and
existing native schema-2 IQ chunks.

```sh
python -m leo.cli.position_scan --host 192.168.1.15 --serial DEVELOPMENT_SERIAL \
  --root /srv/bulk/leo/position-scans --run-id bench --duration 60
python -m pluto_plus.position_scan_verify /srv/bulk/leo/position-scans/bench/wire
```

Add `--dry-run` to inspect the 24-target configuration without storage or radio
access. Use an ABI-3 matched Python environment with the reviewed companion and
tracker sources. The companion holds the shared station serial lock through
preparation, capture and restoration. New RF collection requires explicit user
authorization and a bound of at most 30 minutes.

`native/` contains reopenable native IQ segments. Per-visit metadata retains
global visit, sweep (`visit // 24`), target (`visit % 24`), physical slot,
slot generation, requested and verified IF, axis, counter interval, full raw
receipt and per-RX power. The analysis path is `interior-position`; position
data does not invoke the edge-pilot GLRT. Relay state starts as `unknown` and
requires a per-capture power/timing fit. Preserve both fitted populations and
transition/unknown observations. These IFs use conditional LNB LO hypotheses.

`wire/` contains independently verifiable native v6 receipts and IQ hashes.
`run.json` records a bounded latest-target view, durable counts, terminal and
host restoration. Failed acquisition preserves sealed data and reports failure.
A valid acquisition does not by itself qualify a coordinate decode or establish
that X/Y/Z came from the same spacecraft.
