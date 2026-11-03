# Recorded DS9 source/export qualification

This slice supplies the saved-data side of the additive recorded-plan scanner
composition. `export_recorded_ds9.py` reads the public DS9 store through its
read-only adapter, verifies the frozen capture manifest, re-reads each selected
event and raw CI16 visit, and publishes a new output directory atomically. It
refuses existing destinations and every resolved destination beneath
`/mnt/qnap01` before opening the store. It never deletes or changes public-store
data.

The exporter emits `bundle.json` for provenance and `native.tsv` for the strict
native reader. The native file contains one saved counter/UTC bracket, one
calibration table used for both corrected geometry and ingest authority, and
the original visit IDs, global targets, selection/transition/valid counters,
event hashes, raw hashes and relative raw paths. Historical profile CRC is zero
and its attestation flag is absent. Version 1 accepts only 120-ms dual-RX DS9
visits. Persisted candidate values are not used in the plan.

`device/recorded/recorded_source` copies its configuration, loads at most one
raw visit at a time, checks its exact byte count and SHA-256 before returning a
block, and exposes provider-exact coherent counters with no time or CRC claim.
Target/frequency mismatch, malformed row ordering, unsupported dwell, changed
raw bytes and lifecycle errors fail closed. Cancellation is the only operation
allowed concurrently with acquisition; a leased block prevents destruction.

The one-visit export is original visit 301. The 32-visit export uses the frozen
balanced selection, removes outcome labels from the runtime plan, and orders
rows by original visit/counter. These outputs support sequential recorded-dwell
composition. They do not replay SPF scheduling, feedback, revisit cadence or
RF.

## Results

- Exported visit 301: one 7,200,000-byte raw visit, plan digest
  `2e0cc5446d88cc8bd56794ed10c5d27931654ed1a7ed09ee12a42bba710246c6`.
- Exported panel: 32 visits and four lower-edge target calibrations, plan digest
  `96d495d1781816f15dc73c7548854116ed10a4a91abacdf7b76720619a31a9d2`.
- Strict native input SHA-256 values are
  `963b493007351f8559413fdb8d197f62ba6ab5f07b8f36817ec638c9961dbd82`
  for visit 301 and
  `8f194b6de8cf449d76dbab1683fdf36221f0cc98fdc8c9b6bfcdeb32cc9ebe06`
  for the panel.
- Export validation, provider host tests, the actual visit-301 provider path,
  and ASAN/UBSAN equivalents pass. ARM binaries are cross-built; physical ARM
  execution is root-owned and is not claimed here.

Raw staging remains at `/var/tmp/leo-recorded-ds9-v2/{visit301,panel32}`. The
checked-in `exports` directories intentionally contain metadata only. Their
`SHA256SUMS.json` files bind every staged raw visit for reproducible regeneration
from the public read-only store.

## Reproduction

```sh
sudo -n /var/tmp/leo-arm-realtime-publication/.venv/bin/python \
  export_recorded_ds9.py --scope visit301 \
  --output /var/tmp/leo-recorded-ds9-v3/visit301
sudo -n /var/tmp/leo-arm-realtime-publication/.venv/bin/python \
  export_recorded_ds9.py --scope panel32 \
  --output /var/tmp/leo-recorded-ds9-v3/panel32
/var/tmp/leo-arm-realtime-publication/.venv/bin/python \
  test_export_recorded_ds9.py
```

The component builds use:

```sh
mkdir -p /var/tmp/leo-recorded-source-tmp
TMPDIR=/var/tmp/leo-recorded-source-tmp \
  native/adaptive/device/recorded/build.sh host OUTPUT
TMPDIR=/var/tmp/leo-recorded-source-tmp \
  native/adaptive/device/recorded/build.sh sanitize OUTPUT
TMPDIR=/var/tmp/leo-recorded-source-tmp \
  native/adaptive/device/recorded/build.sh arm OUTPUT
```

The recorded scanner runner and final `Analysis` composition are separate
owned slices. Until those pass, this report qualifies only export authority and
the read-only source provider.
