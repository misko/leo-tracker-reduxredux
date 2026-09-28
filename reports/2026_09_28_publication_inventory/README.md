# Report publication snapshot — 2026-09-28

This publication adds the local report backlog and its portable evidence to the
current remote main without replacing unrelated application work. See the
[full Markdown inventory](REPORTS.md) and [file manifest](manifest.json).

Reports retain their scientific status: completed negative results, failed
attempts, protocols and ongoing-build status documents are all preserved. A
published protocol is not a claim that its experiment has finished. No new radio
campaign was run to make publication possible.

## What is included

Missing report prose, figures, numerical JSON/JSONL evidence, resource/launch
receipts, report scripts, receiver/DS7 research tools and their local tests are
included. Research files are published as evidence; this commit does not deploy
them or change the application implementation. Existing remote report content
is retained. Where local prose differs from remote prose, both are preserved:
remote remains canonical and the local snapshot is under `local-variants/` with
its original path recorded in the manifest. Those archival copies retain their
original text and relative link conventions; consult the canonical report path
for rendered navigation.

Generated compiler work/build trees, executable binaries, IQ arrays, binary
working caches, process IDs and profiler dumps are excluded and inventoried.
Their exclusion does not turn a report's source-corpus reference into a bundled
recording. Raw recordings and reference corpora remain external dependencies.
The manifest records the publication boundary, rather than claiming every file
on the research machine belongs in Git.

## Large evidence files

Fifty numerical evidence files larger than 10 MB are stored as deterministic
gzip files alongside their intended original paths. This keeps every Git blob
below GitHub's 100 MB limit. The reports and their original evidence indexes
retain original filenames and hashes. Restore those filenames after cloning:

```bash
python3 reports/2026_09_28_publication_inventory/restore_evidence.py --check
python3 reports/2026_09_28_publication_inventory/restore_evidence.py --restore
```

The check verifies publication hashes and decompressed original bytes. Restoration
is limited to this checkout and refuses to replace a differing existing file.
On GitHub, download the corresponding `.gz` for an original JSON/JSONL link that
is absent; the exact mapping is in `manifest.json`. Compressed files are evidence
archives, not revised datasets.

## Completeness and integrity checks

The publication audit resolves all relative file links in newly published
canonical Markdown to a file, directory, pre-existing remote object or restorable
gzip archive. Linked locally ignored figures and tables were explicitly included.
It preserves reports already published identically rather than duplicating them.

Receiver evidence indexes verified **739 original bindings**. One pre-existing
exception remains: `reports/2026_09_28_rx_geometry_association/README.md` does not
match the historical README hash in its own evidence index. The numerical/source
bindings checked in that audit matched. This publication preserves both the
current README and historical index without silently resealing or claiming the
prose matches its older hash. See [integrity-audit.json](integrity-audit.json).

This is a publication/completeness audit, not a new scientific validation of
every historical experiment. Each report retains its original test results,
limitations, failures and outstanding next steps. The latest receiver-state
experiment, for example, reports no validated association gain; its failed
development gate remains explicit.
