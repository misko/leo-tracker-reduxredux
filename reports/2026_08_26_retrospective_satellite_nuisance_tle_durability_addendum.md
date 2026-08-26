# Retrospective satellite nuisance: TLE replay-durability addendum

## Disposition

This is a **post-outcome maintenance correction**, not a new experiment or an
independent confirmation. The retrospective association outcomes were already
visible when the replay defect was found. No IQ was read, no candidate was
propagated or refit, and no report, evidence, ranking, metric, gate, figure, or
conclusion was regenerated.

The original frozen protocol correctly recorded the archive-index digest used
to discover its TLE snapshots. The runner incorrectly re-read that same
mutable index path and required its bytes to remain unchanged forever. The
collector subsequently appended newer snapshots, so the live index advanced
from frozen SHA-256 `1397ff2c...` to the observed `a0e6c662...` and an otherwise
valid replay failed before loading its already frozen inputs.

The correction makes that historical index **provenance-only**. Replay now
uses the exact content-addressed raw TLE bytes and their timestamp-specific,
immutable snapshot metadata as authority. It never reads the current index and
never rediscovers or substitutes a snapshot.

## Frozen maintenance authority

The
[durability amendment](../config/analysis/retrospective-satellite-nuisance-tle-durability-amendment-v1.json)
was committed first at `ace0200d0516650091e2124f0837d8589313381a`, before the
loader correction. Its SHA-256 is
`d7048ff6fd17ae0b773a1031ddf37b04930b407e8dfb00e1cb5f655dd61ca404`.
It binds:

- the unchanged original [protocol](../config/analysis/retrospective-satellite-nuisance-protocol-v1.json),
  SHA-256 `fb94236e...`, initially frozen at `0b4bae8...` and finally bound
  before execution at `7648878...`;
- the historical mutable-index path and frozen SHA-256 `1397ff2c...`, explicitly
  with no current or historical index bytes required for replay;
- all exact raw catalogues, their byte sizes, and all four immutable
  timestamp-specific snapshot metadata records;
- the [latest-causal TLE reconstruction authority](../config/analysis/retrospective-satellite-nuisance-latest-tle-reconstruction-v1.json),
  SHA-256 `7748e159...`, and its exact NORAD 47657 replacement record,
  SHA-256 `7dc3afac...`; and
- the sealed result report, machine evidence, and artifact-manifest hashes.

| Capture | Retrieved UTC | Raw TLE SHA-256 | Immutable metadata SHA-256 |
|---|---:|---:|---:|
| `065355` | `05:37:00.001167Z` | `ca5345a8...` | `d604e9f1...` |
| `103607` | `09:37:00.001376Z` | `ffec9470...` | `ce445f55...` |
| `130425` | `11:37:00.000955Z` | `ac79e846...` | `9cfd6983...` |
| `150802` | `13:37:00.001273Z` | `ac79e846...` | `fe8de7ff...` |

The last two rows intentionally share identical catalogue bytes but have
different immutable metadata and retrieval timestamps. Both metadata receipts
are therefore retained; a content digest alone cannot establish which causal
collection event preceded a dwell.

The 150802 source-sensitivity catalogue remains a deterministic byte-exact
reconstruction of the historical 14:02 source. Replay must reproduce SHA-256
`9bb59fcf...` and 10,972 objects without consulting its obsolete temporary
path.

## Fail-closed replay behavior

The runner pins the amendment bytes and the original protocol bytes. It then
checks, for every capture, the raw path, SHA-256, byte size, parsed object count,
metadata SHA-256 and schema, raw-object identity, exact retrieval timestamp,
first-measurement timestamp, and strict pre-dwell causality. It separately
checks the latest-source reconstruction authority and replacement record.

Tests exercise four independent failure modes: altered raw TLE bytes, altered
snapshot metadata bytes, a cross-bound timestamp change, and reconstruction-
authority drift. A guard test makes any attempt to read the mutable index fail,
while the valid frozen replay continues to load successfully.

## Sealed outcome preservation

The original
[results report](2026_08_26_retrospective_satellite_nuisance_results.md)
remains byte-identical at SHA-256 `109bda80...`; the original machine evidence
remains `14966c48...`; and its artifact manifest remains `5e87fa35...`. Thus the
published disposition is unchanged: four recoverable tracks, zero
candidate-evidence passes, and zero secure NORAD identities. This correction
restores durable input verification only.
