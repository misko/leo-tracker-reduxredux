# Starlink literature and external datasets

## Motivation

Keep the public waveform literature, its claim boundaries, and usable external
recordings together so research can build on measured signal structure.

## Problem

Papers, raw IQ, demodulated symbols, spectrum scans, and network measurements
are frequently described as “Starlink data” despite supporting different claims.
Downloaded material must not enter Git or silently become a scientific golden.

## Solution

Version the reviews and provenance here; keep downloaded papers, third-party
code, and datasets in the Git-ignored `local/` directory. Start with the small
UT full-channel recording. Large datasets are cataloged separately.

## Method

Initial review: 2026-09-27, based on primary papers, author repositories,
dataset documentation, and inspection of the UT IQ ZIP. This is a focused
review, not an exhaustive systematic review. No RF collection is involved.
Downloads are reference material, never application runtime dependencies.

## Contents

- [Expanded technical review — 2026-09-28](broad-review-2026-09-28.md):
  navigation/receivers, networking, Direct-to-Cell, security, astronomy, and environment.
- [Expanded source index and local PDF links](source-index-2026-09-28.md)
- [Search scope, reading depth, and access gaps](search-notes-2026-09-28.md)
- [2026-09-28 download provenance](downloads-2026-09-28.json): additive
  manifest with successful PDFs/article snapshots and failed requests.
- [Public firmware leads for header decoding](firmware-leads.md)
- [Receive-MAC header parsing evidence from firmware](firmware-header-analysis.md)
- [State of the art and paper reviews](review.md)
- [Cleartext, satellite identity, timing, and orbit investigation](identity-timing-orbit.md)
- [UT raw-IQ header reproduction](../../../reports/2026_09_27_ut_header/README.md)
- [DS7 pilot isolation and bounded header search](../../../reports/2026_09_27_ds7_header/README.md)
- [Dataset catalog and interpretation limits](datasets.md)
- [Download provenance](downloads.json): source URLs, local relative paths,
  byte counts, and SHA-256 hashes of successfully downloaded files.
- `local/papers/`: local PDF copies; exact versions appear in the manifest.
- `local/sources/`: local copies of supporting author pages and documentation.
- `local/data/ut-pilots/`: raw-IQ ZIP, extracted waveform, and small supplements.

`local/` is intentionally absent in a fresh clone. The URLs in `downloads.json`
identify the downloaded artifacts; hashes identify the reviewed copies. Files
in `local/` are not staged or committed. Never use `git add -f` on them.

## Review workflow

1. Record the title, authors, version/date, primary URL, and evidence type.
2. Distinguish measured facts, author interpretations, and our proposed uses.
3. Classify data before downloading: real IQ, demodulated symbols, spectra,
   simulation, or network measurements. Record bandwidth separately from rate.
4. Save external material under `local/`; record its URL and digest in the
   manifest. Preserve third-party license files and attribution.
5. Link any reproduction to an exact source/data digest and a bounded report.
   External data do not become golden fixtures without explicit review.
6. Revisit version-sensitive conclusions when a paper or waveform changes.

For repository-qualified claims, use the existing
[evidence ledger](../evidence-ledger.md) and
[Starlink transmission concepts](../../concepts/starlink-transmissions.md).
This catalog does not promote published results into local validation results.
