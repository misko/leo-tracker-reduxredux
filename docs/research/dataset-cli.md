# Dataset inventory CLI

List the frozen scientific DS dataset memberships from any installed checkout:

```bash
uv run leo datasets list
uv run leo datasets list --scan-type fast
uv run leo datasets list --dataset DS26 --dataset DS27 --json
uv run leo datasets list --all-revisions
```

The table prints dataset ID, revision, number of scans, fast/adaptive/legacy-hop
counts, unknown-mode counts, and sample-rate counts in **MS/s**. For example,
`2.5: 302, 10: 111` means 302 acquisitions at 2.5 MS/s and 111 at 10 MS/s.
JSON also provides the joint recording-type/sample-rate breakdown and the source
paths and SHA-256 checksums. Dataset selection is case insensitive; repeat
`--dataset` to select multiple datasets. `--catalogue PATH` reads another snapshot.

The current catalogue includes DS1–DS28, the historical DS2-22 successor and DSX01.
DS14, DS15 and DS19 have unlocated membership authorities and display `unlocated`,
not zero scans. Default output selects the current revision; `--all-revisions`
also displays the original DS24 and DS28 snapshots separately.

Counts describe whole member acquisitions, including incomplete members, rather
than only successful analyses. For example, current DS26 has **317 scans: 159
fast and 158 adaptive**; the fast-only filter returns 159. DS25 remains the
adaptive-only overlapping cohort. Memberships can overlap across datasets and
revisions, so table rows must not be summed into a corpus total. DS1 nested views
count unique session IDs, excluded DS4 candidates are omitted, and DSX01 counts
its five source scans rather than its fifteen overlapping challenge regions.

`Hop` identifies historical hopping recordings whose membership metadata does not
establish the active adaptive policy. It must not be interpreted as definitely
non-adaptive. Unknown sample rates stay unknown; the tool does not assume that
fast means 10 MS/s or use the radio's restoration settings as capture settings.

## Updating the catalogue after minting a dataset

Listing is offline and reads a small packaged metadata snapshot, generated on
November 3, 2026. It does not discover new recordings, read IQ, query PostgreSQL,
or change dataset membership. This keeps listing quick even when a historical
authority contains hundreds of megabytes of embedded metadata.

Register a newly minted membership in `EXTRA_AUTHORITIES` in
[`tools/build_dataset_catalogue.py`](../../tools/build_dataset_catalogue.py), and
rebuild the snapshot:

```bash
PYTHONPATH=src python tools/build_dataset_catalogue.py \
  --repo . \
  --resolve-recording-metadata \
  --output src/leo/cli/dataset_catalogue.json
```

Use repeated `--source-root /path/to/checkout` if authorities live in another
checkout. The builder tries the selected repository, those additional roots, and
then that repository's `HEAD` Git objects for sparse checkouts. DS28 revision 2's
membership authority currently requires a source root containing its frozen
report directory. Missing required membership authorities are errors.

The builder verifies archived part checksums and the recovered original authority
checksums. `--resolve-recording-metadata` optionally reads checksum-bound capture
manifests for missing sample rates or modes, including DS23's pinned raw metadata.
Unavailable optional metadata remains unknown; changed capture metadata is an
error. Acquisition settings are kept separate from restoration and analysis
settings. No IQ payloads are read, copied or changed. Review the generated diff
and run `tests/cli/test_datasets.py` before publishing the updated snapshot.
