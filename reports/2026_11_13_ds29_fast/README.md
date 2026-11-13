# DS29 revision 1: all fast acquisitions after DS28

DS29 contains **615 whole fast acquisitions** after DS28 revision 2. It retains
**612 complete and 3 incomplete scans**, including the three without published
tracking inputs: DS29-0073, DS29-0258 and DS29-0259. All members were captured
at 10 MS/s. Analysis readiness, completeness, channel coverage, signal quality
and localization results do not determine membership.

The frozen acquisition-start interval is
**[2026-11-01T14:39:47.024292987Z, 2026-11-13T04:55:00Z)**.
The lower boundary is DS28 revision 2's exact cutoff. Actual member starts span
2026-11-01T15:24:20.225325720Z through 2026-11-13T04:35:42.381528643Z.

| Property | Count |
|---|---:|
| Fast acquisitions / unique content identities | 615 |
| Complete / incomplete acquisitions | 612 / 3 |
| Existing published tracking inputs | 612 |
| Adaptive acquisitions included | 0 |
| Adaptive manifests excluded by format | 612 |
| Discovery roots / checked manifests | 24 / 25,443 |
| Recorded windows | 4,152,239 |
| Referenced compressed recording bytes | 5,024,336,021,239 |
| Reported metadata/index integrity errors | 0 |
| Discovery errors / DS28 content overlaps | 0 / 0 |

The corpus remains in place. Minting read metadata and indexes, checked reported
payload sizes, and verified source metadata commitments. It did not copy or
rehash IQ payloads, start RF collection, or modify QNAP paths. The snapshot is
not an atomic view of concurrent recording activity.

## Authorities and verification

The [exact compressed manifest](dataset/manifest.json.gz) is the complete
authority. Its uncompressed SHA-256 is
`b9b7dfc497f1df45e913e175be9b9471b1e0b49eab601f0aeff640c5c05c61a8`.
The 92 MiB uncompressed document is stored as deterministic gzip to limit
repository growth. Decompress it to `dataset/manifest.json` in a fresh copy
before checking every entry in the original [seal](dataset/seal.json).

Supporting artifacts are the [membership summary](dataset/membership-summary.json),
[evaluation units](dataset/evaluation-units.json), [all-member sample](dataset/sample.json),
[discovery census](dataset/discovery.json), [original parent bytes](dataset/parent-manifest.json),
and [mint verification](dataset/verification.json).

[Independent verification](independent-verification.json) rechecked 10,424 source
metadata hashes, every acquisition timestamp and content identity, exact interval,
parent preservation, source code hashes and seal. A separate
[review](ds29-mint-review.md) reconciled every one of the 615 discovered fast
roots to a retained member or its duplicate roots. No eligible root was omitted.

Three behavioral tests cover acquisition boundaries, whole acquisitions spanning
the boundary, duplicate identities, parent overlap, empty failed recordings,
arbitrary rates/channels, unavailable analysis and adaptive exclusion. Two
explicit adapter differences from DS28 are recorded in the manifest: consistent
actual-sample acquisition times and metadata identities for empty failed scans.
DS28's published authority remains byte-for-byte unchanged.

## Reproduction

Use [freeze_ds29.py](dataset/tooling/freeze_ds29.py) with its pinned support
adapters and [tests](dataset/tooling/test_freeze_ds29.py). From a checkout with
the repository virtualenv, set `PYTHONPATH=src:tools` and disable bytecode writes.
Supply `--parent` with `dataset/parent-manifest.json`, `--cutoff-ns
1794545700000000000`, and a fresh local `--output`. Historical corpus permissions
require the same read access as the original census. The tool refuses to replace
an existing frozen membership. Writes stay inside the new output directory.

The separate [verifier](dataset/tooling/verify_ds29.py) recomputes identities,
acquisition times and source commitments. Its source paths refer to the original
frozen corpus and tooling; all pinned originals are retained under
`/srv/bulk/leo-dev/ds29-20261113`.

## Fixed fast-algorithm evaluation

The user requested full DS26 fast-subset and DS29 evaluation of fixed algo07v5
with zero RF recovery targets against frozen original algo07v3. The algorithm
and numerical precision are fixed before DS29 outcomes are inspected. Missing
members stay in both denominators. Controlled c=0 and fitted-c position errors
will be reported separately from frequency fit and association coverage.

Reproducible inputs and evaluation work live under
`/srv/bulk/leo-dev/ds29-20261113/snapshot` and
`/srv/bulk/leo-dev/ds26-ds29-evaluation-20261113`. Full comparison and repeated
timing results are pending. DS29's reference-coordinate audit uses the operator
station authority; these coordinates are not an independent surveyed GNSS fix.

The verified evaluator snapshot contains 612 available native inputs and the
three missing cases above. Inventory SHA-256 is
`5e4c8505ac6aff55fbe296aeff1874c0a5dcd7fe11ea0e314d108caaf86e91ac`.
It freezes 223 unique causal TLE snapshots and the unchanged DS26 configuration.
Pass its `evaluation-references.json` explicitly when using the shared evaluator;
the DS29 template has no evaluation-reference fallback.

The full campaign launched at 2026-11-13T05:32:07Z. It retains 159 DS26 and
615 DS29 cases, with 770 available pairs and all four missing-input cases.
Its `run_campaign.py` coordinates four fixed accuracy lanes, verified NVMe
staging/bulk archives, five serial repetitions on each predeclared sample case,
and final public-evidence validation. See
[the investigation checkpoint](../../docs/analysis/algo07v4-v5-goal.md).
