# DS10: analysis-complete recordings after DS9

Publication note: this is the parent dataset for the [DS11 benchmark](../2026_09_30_ds11_single10/README.md). The original introduction referenced a separate, unpublished DS7–DS10 symbol-analysis report; its exact wording is retained in the [historical README](../2026_09_30_ds11_publication/historical-reports/DS10-README.md).

**Minted: 187 recordings, 414,161 visits, and 13.8054 hours of valid IQ per
receiver.** Eight of 195 candidates were excluded for incomplete analysis.

| Property | Frozen value |
|---|---:|
| First admitted capture starts | 2026-09-28 13:00:15.689238 UTC |
| Last admitted capture ends | 2026-09-29 12:55:05.057462 UTC |
| Valid IQ per receiver | 49,699.32 seconds |
| Compressed IQ referenced in place | 2,164,286,726,125 bytes / 2.1643 TB |
| 2.5 / 5 / 7.5 / 10 MS/s recordings | 36 / 29 / 37 / 85 |
| Chronological groups of eight / remainder | 23 / 3 recordings |

All 187 admitted recordings reported GLRT `figures_ready` and tracking
`complete`. Three excluded candidates had ready GLRT but incomplete tracking;
five had incomplete GLRT and tracking. Calendar span is not uninterrupted IQ
exposure. DS10 is disjoint from DS7, DS8 and DS9 by both session ID and source
manifest digest.

DS10 freezes existing recordings at **2026-09-29 13:48:48 UTC**. The lower
boundary is DS9's last admitted capture end, **2026-09-28 12:58:13.169402 UTC**,
not DS9's later inventory cutoff. Membership does not grow as analysis finishes.

The authoritative membership is [local/manifest.json](local/manifest.json).
[local/candidate-index.json](local/candidate-index.json) freezes the candidate
inventory, and [local/evaluation-units.json](local/evaluation-units.json) provides
individual recordings, chronological groups of eight, rate strata and the full
dataset. These are evaluation views, not train/test partitions. Both receivers
stay together in each recording.

## Admission

The admission rules follow DS9: published, finalized, UTC-qualified captures
strictly after the parent boundary and ending by the cutoff; completed zero-error
capture terminals, complete retained visits, attested source spans, nonempty IQ,
restored radio state, and no reported missing/unclassified samples or dropped
events. Retune-invalid samples are accounted separately.

Analysis must have complete **120 ms-stride production GLRT** visit coverage,
a sealed metrics manifest, and a complete tracking product with complete
trajectory and TLE stages. Session and raw-manifest bindings must match, and the
tracking input must name the exact GLRT metrics digest. Tracking product creation
must be no later than the fixed cutoff. Deferred candidate groups are allowed,
as in DS9; completion does not mean exhaustive satellite identification or
successful decoding of message bytes.

The candidate list was frozen first. Readiness was observed over the subsequent
inventory interval, not in an atomic database snapshot. Full read-only API
responses and exclusion reasons are preserved for every candidate. No new
analysis or RF acquisition was launched. No additional signal-quality or sample
rate selection is applied.

## Storage and verification

IQ remains in its source store, referenced by session and manifest digest.
Minting validates sealed metadata and chunk accounting through the public
read-only reader; it does not copy, decompress or rehash IQ. DS10 is not a backup
or enforced retention hold. Pose companions are not collected for this snapshot;
their absence is not an admission filter, and DS9's pose authority is not assumed
to extend to new recordings.

All generated membership, analysis receipts and working checkpoints are beneath
Git-ignored `local/`. Source, tests and this summary can be versioned separately;
the dataset contents are not committed. The manifest binds DS9's exact digest.
`local/SHA256SUMS` seals membership, evaluation views, candidate inventory,
receipts, and mint/test source.

Offline verification requires Python's standard library:

```sh
python3 reports/2026_09_29_ds10_post_ds9/mint.py verify
```

Validation at mint: **17 tests passed**, Ruff checks passed, DS9 parent
verification passed, and DS10's sealed offline verification passed.

`mint.py collect` checkpoints metadata-only batches. `mint.py seal` and `collect`
refuse to overwrite a sealed dataset. The fixed cutoff is intentionally part of
this snapshot's source. Admission and sealing tests run without hardware,
database or storage access:

```sh
.venv/bin/python -m pytest -q reports/2026_09_29_ds10_post_ds9/test_mint.py
```
