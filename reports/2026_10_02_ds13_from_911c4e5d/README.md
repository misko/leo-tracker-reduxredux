# DS13: complete scans from scan-fw-911c4e5db9243281

DS13 contains **17 recordings with complete production GLRT and tracking analysis**,
starting inclusively at `scan-fw-911c4e5db9243281`. All 28 published scans in the
requested time window were inspected; 11 with unfinished analysis were excluded.
The authoritative membership is [local/manifest.json](local/manifest.json).

| Property | Frozen value |
|---|---|
| Snapshot cutoff | October 2, 2026, 9:46:54 a.m. PDT (16:46:54 UTC) |
| First admitted capture start | October 2, 2026, 2:46:26.922392 a.m. PDT (09:46:26.922392 UTC) |
| Last admitted capture end | October 2, 2026, 8:57:14.568333 a.m. PDT (15:57:14.568333 UTC) |
| Last admitted scan | `scan-fw-ffa1cc19d8d7c09f` |
| Admitted / excluded candidates | 17 / 11 |
| Retained IQ visits | 37,661 |
| Valid IQ duration per receiver | 4,519.32 seconds (75.322 minutes) |
| Referenced compressed IQ | 150,671,288,573 bytes (150.67 GB) |
| 2.5 / 10 MS/s recordings | 10 / 7 |
| Receivers / radio | RX0 and RX1 / `radio_pluto_5d4d` |
| Chronological groups of eight / remainder | 2 / 1 |

## Membership and completion

The lower boundary is the requested scan's qualified capture-start estimate,
included in membership. This is a new dataset with an explicit starting scan,
not an extension from DS12's last recording. DS12's existing checksum and semantic
verification passed unchanged. DS13 is disjoint from DS12 by session ID, input
manifest digest, and uncompressed IQ digest.

Admission reuses the frozen DS11 complete-capture and production-analysis checks:
complete capture and sample accounting, qualified timing, completed restoration,
capture finalization by cutoff, full 120 ms-stride GLRT visit coverage, and an exact
raw-manifest → GLRT-manifest → tracking-product binding. Tracking, trajectory, and
TLE stages must be complete, with the tracking product created by cutoff.
No sample-rate, localization-result, or signal-quality ranking selects scans.

“Complete analysis” means the configured production pipeline completed. Its
tracking candidate-group limits and deferred groups remain preserved in the
saved responses; this does not claim exhaustive analysis of every candidate group.

## Exclusions

All 11 excluded candidates lack complete tracking analysis. Three also have
partial GLRT coverage. Four have missing-sample/incomplete-visit capture flags;
these overlap the analysis exclusions, so no scan with complete analysis was
removed solely by a capture-quality gate.

| Scan | Analysis state observed during inventory |
|---|---|
| `scan-fw-80ff1dc1f735c034` | GLRT ready; tracking pending |
| `scan-fw-22a8c0707af68c26` | GLRT ready; tracking pending |
| `scan-fw-ba069f447a5090dd` | GLRT ready; tracking running, product created after cutoff |
| `scan-fw-f8b832233979e2ab` | GLRT ready; tracking pending |
| `scan-fw-66a1971e9bce28d7` | GLRT ready; tracking pending |
| `scan-fw-5ccca4f953b0ee7e` | GLRT ready; tracking pending |
| `scan-fw-e032e03e050f4f52` | GLRT ready; tracking pending |
| `scan-fw-e1eeed445d5c033a` | GLRT ready; tracking pending |
| `scan-fw-807c6455098e6e0c` | GLRT partial; tracking pending |
| `scan-fw-9a22f6ea0a01be13` | GLRT partial; tracking pending |
| `scan-fw-f75cc82682ca80b2` | GLRT partial; tracking pending; capture finalized after cutoff |

The manifest preserves every exclusion reason. Later completion does not change
this frozen snapshot. Readiness was observed over the inventory interval and
tracking creation was bounded by cutoff; this is not an atomic database snapshot.

## Artifacts and verification

- [Membership and exclusions](local/manifest.json).
- [Frozen source index and inclusive boundary](local/candidate-index.json).
- [All inspected candidates](local/inventory.json).
- [Singles, groups of eight, full membership, and rate strata](local/evaluation-units.json).
- [Checksum seal](local/SHA256SUMS), binding metadata snapshots, full analysis
  responses, membership, evaluation views, collection code, tests, the reused
  admission implementation, and the DS12 parent manifest.

Nine DS13 tests and all 17 reused DS11 admission tests pass. Offline checksum and
semantic verification passes, including inclusive membership, complete candidate
accounting, analysis provenance, chronological evaluation views, and DS12
disjointness. The tests also reject stale products, post-cutoff completion,
missing inventory rows, seal tampering, overwrites, and API service failures.

To verify from the repository root:

```sh
python3 reports/2026_10_02_ds13_from_911c4e5d/mint.py verify
.venv/bin/python -m pytest --import-mode=importlib \
  reports/2026_10_02_ds13_from_911c4e5d/test_mint.py \
  reports/2026_09_30_ds11_post_ds10/test_mint.py -q
```

Raw IQ remains referenced in its existing store. This is a local metadata and
analysis-evidence snapshot, not an IQ backup or retention hold. Raw chunks were
not independently checked, decompressed, or rehashed. Pose companions were not
collected. No RF acquisition, re-analysis, publication, or service change was
performed. Snapshot payloads under `local/` are Git-ignored.
