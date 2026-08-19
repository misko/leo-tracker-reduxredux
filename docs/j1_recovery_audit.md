# J1 IQ and calibration recovery audit

Audit completed: 2026-08-19T04:08:59Z UTC.

Result: **not recovered**. Neither the immutable 1.2 GB IQ object nor its
200,000-byte selected window is available at any exact, documented retention
location checked below. The frozen calibration object is also unavailable by
its asserted digest. ADR 0006 Option B now records J1 as
`UNAVAILABLE_HISTORICAL_EVIDENCE`; this audit supplies no basis for a parity,
calibrated-detection, or specificity claim.

This was a read-only, targeted audit. It did not modify QNAP, hash arbitrary IQ
files, or recursively traverse the active acquisition/soak trees. Searches
were limited to exact identities, exact documented paths, shallow archive
inventories, and the historical catalog.

## Frozen identities

| Object | Required evidence |
|---|---|
| Full dual-RX CI16 IQ | 1,200,000,000 bytes; SHA-256 `23cceb3a5223180ff92398214125513d4c32cc541ec1ae5b7c4c28fba5bbcc8c` |
| J1 41.6 s slice | offset 832,000,000; 200,000 bytes; SHA-256 `4fbd775f850124dab038e70dadba1ce1cbbfc16ebe58d9fb425430b51d61ce02` |
| Frozen calibration | SHA-256 `141a489a08f236839cd1cbec8d31cc31611abd5941b91bca7269974b53d17f8d` |

The source report fixes the IQ geometry as dual-receiver little-endian CI16 at
2.5 MS/s and identifies recording
`rec_01M09J1R6E59GCC8ANJVYVRN1B`. Textual reports and plots are provenance,
not substitutes for these bytes.

## Exact local-object checks

- The documented full-IQ path
  `/home/mouse9911/.local/share/leo-flow/objects/sha256/23/23cceb3a5223180ff92398214125513d4c32cc541ec1ae5b7c4c28fba5bbcc8c`
  is absent. Its `23` prefix directory is itself absent.
- The exact selected-slice CAS path under prefix `4f` is absent. That prefix
  contains one unrelated 2,848-byte object named
  `4fc27296120a86e03f1ed1b1e331487d8f46a02f5b8d3826cbde801ecf3b6ce3`.
- The report's metadata and manifest CAS prefixes (`87` and `94`) are also
  absent. This is consistent with removal of the earlier CAS generation, but
  is not evidence about why it disappeared.
- `/srv/bulk/leo/test-corpus/j1-calibrated-positive-41p6/recording.ci16`
  is absent. The protected corpus presently contains RETRO's 200,000-byte IQ
  fixture, not J1.
- Exact historical scratch outputs
  `/tmp/j1-analysis/`, `/tmp/j1-oracle-capture/recording.ci16`, and the four
  named 41.6/58.5-second symbol archives are absent.

Minimal reproduction:

```bash
stat \
  /home/mouse9911/.local/share/leo-flow/objects/sha256/23/23cceb3a5223180ff92398214125513d4c32cc541ec1ae5b7c4c28fba5bbcc8c \
  /home/mouse9911/.local/share/leo-flow/objects/sha256/4f/4fbd775f850124dab038e70dadba1ce1cbbfc16ebe58d9fb425430b51d61ce02 \
  /srv/bulk/leo/test-corpus/j1-calibrated-positive-41p6/recording.ci16 \
  /tmp/j1-oracle-capture/recording.ci16
```

All four paths return `ENOENT` as of the audit time.

## Reports and retained derived objects

The historical Redux asset directory contains only JSON and PNG outputs. It
contains no `.ci16`, `.npz`, or other raw/symbol archive:

`/home/mouse9911/gits/leo-tracker-redux/reports/rec_01M09J1R6E59GCC8ANJVYVRN1B_assets`

The JSON files retain the expected hashes, geometry, epochs, CFOs, and QAM
summaries. PNGs retain visualizations. Neither representation is invertible to
the original CI16 window, so regenerating bytes from those products would be
fabrication rather than recovery.

Exact-hash and recording-ID searches in `leo-tracker`, `leo-tracker-redux`,
the new corpus declarations, and the installed release manifests found only
textual provenance/oracle references. No file with either required IQ digest
was found.

## Historical catalog check

The retained Forward-v2 PostgreSQL instance was queried with
`default_transaction_read_only=on`. Exact predicates were used for the
recording ID and the full IQ, selected slice, metadata, and manifest digests.

- `recording`: no J1 row.
- `object_blob`: no row for any of the four exact digests.
- retention batch, staging, and GC-attempt tables: no exact-digest event.

This database contains only eight recordings published from
2026-08-18T20:50:42Z onward. J1 was captured at approximately
2026-08-18T04:28:36Z. Therefore the negative query proves only that this newer
catalog cannot recover or explain J1; it does **not** prove a retention delete.

## QNAP and archive checks

- QNAP was read only throughout.
- `/mnt/qnap01/mouse9911/leo-store` has the separately archived
  `2026_08_17_RETRO_QAM` corpus and no J1 archive at its shallow inventory.
- Exact 2026-08-18T04 capture/staging names derived from J1's frozen capture
  time are absent from `/mnt/qnap01/mouse9911/leo/captures` and
  `/mnt/qnap01/mouse9911/leo/staging`.
- `/mnt/qnap01/@Recycle/mouse9911` and
  `/mnt/qnap01/@Recently-Snapshot` contain only their `desktop.ini` entries at
  the mounted shallow inventory. They expose no retained J1 object.
- The documented dashboard endpoint
  `http://gauss:8090/recordings/rec_01M09J1R6E59GCC8ANJVYVRN1B` is no longer
  listening, so it cannot resolve another locator.

No broad QNAP content hashing was performed. An undisclosed offline backup may
still exist, but this machine has no evidence of one and this report does not
claim otherwise.

## Calibration check

The mutable path
`/mnt/qnap01/mouse9911/leo/reports/lnb-calibration.json` is 950 bytes and hashes
to `7b9db0551e8c6520ae18e81d89c90459464ce558fc791ff07bf5ae77149c659d`,
not the frozen J1 digest. It presently reports the historically relevant
`pluto-19f2` mismatch of 602,869.4 Hz, but matching a numerical field does not
establish byte identity or immutable provenance.

The only documented pre-swap backup exists both on QNAP and in `leo-tracker`;
both 949-byte copies hash to
`cd0e407f1e50e6ce90a0be61289d2d731101c719884c5af25faa88d3cd3aa785`.
The checked-in live-calibration snapshot hashes to
`c8aa09331cf6f8c502b6ee6782074f3374d6451b20916117a116fd40d8aa8287`.
None matches the required frozen calibration digest.

## Recovery acceptance rule

J1 can leave `UNAVAILABLE_HISTORICAL_EVIDENCE` only after one of these
succeeds:

1. recover the 1.2 GB object and verify its exact size and full SHA-256, then
   verify the declared slice hash; or
2. recover an independently retained 200,000-byte slice and verify the exact
   slice SHA-256, while explicitly limiting claims to slice-level parity.

Calibration-dependent parity additionally requires recovery of the exact
frozen calibration object or a separately reviewed immutable calibration
authority with an explicit provenance migration. The current mutable JSON may
not be silently blessed as equivalent.
