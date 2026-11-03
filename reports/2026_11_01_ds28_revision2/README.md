# DS28 revision 2 — all fast acquisitions after DS27

DS28 revision 2 contains **16 fast scans**, including **8 newly added scans**. All are complete 10 Msps recordings. The original eight members retain their DS28-0001 through DS28-0008 identifiers; new members are DS28-0009 through DS28-0016. Revision 1 and its evaluation artifacts are unchanged.

The frozen acquisition-start interval is **October 31, 2026, 07:34:49 PDT through November 1, 2026, 06:39:47 PST**, inclusive at the DS27 boundary and exclusive at the new cutoff. The timezone change reflects the end of daylight saving time. Exact nanosecond boundaries are in the manifest.

| Property | Count |
|---|---:|
| Fast acquisitions | 16 |
| Retained from revision 1 | 8 |
| Newly added | 8 |
| Complete recordings | 16 |
| Adaptive acquisitions included | 0 |
| Existing published GLRT/tracking inputs | 15 |
| Recorded windows | 108,358 |
| Compressed recording bytes | 131,660,350,527 |
| Reported metadata integrity errors | 0 |

DS28-0016 has no existing published GLRT/tracking input at freeze time and remains a dataset member. Analysis availability is not a membership filter. Existing input availability does not establish successful localization; previous DS28 performance results cover revision 1 only.

## New members

| ID | Acquisition start, local time | Recording | Existing GLRT input |
|---|---|---|---|
| DS28-0009 | October 31, 20:46:07 PDT | Complete | Yes |
| DS28-0010 | October 31, 22:36:24 PDT | Complete | Yes |
| DS28-0011 | November 1, 00:06:39 PDT | Complete | Yes |
| DS28-0012 | November 1, 01:36:54 PDT | Complete | Yes |
| DS28-0013 | November 1, 02:07:08 PST | Complete | Yes |
| DS28-0014 | November 1, 03:17:21 PST | Complete | Yes |
| DS28-0015 | November 1, 04:47:35 PST | Complete | Yes |
| DS28-0016 | November 1, 06:17:49 PST | Complete | No |

## Authorities and checks

- [Frozen manifest](dataset/manifest.json), [compressed copy](dataset/manifest.json.gz), and [digest](dataset/manifest.sha256).
- [Membership summary](dataset/membership-summary.json), [evaluation units](dataset/evaluation-units.json), and [all-member inventory](inventory.csv).
- [Discovery census](dataset/discovery.json), [metadata verification](dataset/verification.json), [revision verification](revision-verification.json), and [seal](dataset/seal.json).
- [Original DS28 manifest](dataset/previous-revision-manifest.json) and [DS27 parent manifest](dataset/parent-manifest.json) are preserved byte for byte.

Manifest SHA-256: `6bf59b01b5fbf72b42fafee2445cafde3c3660a10b0cb048a98a8340a2329e71`.

Membership uses whole fast acquisitions starting after the DS27 boundary, across all discovered recording roots. It does not select on channel coverage, signal quality, sample rate, analysis readiness, completeness or localization outcome. Duplicate physical identities are collapsed; no member overlaps DS27. All previous DS28 identities and labels are preserved.

The census reads recording metadata and existing public analysis contracts. Referenced metadata is rechecked before sealing; recording payloads are not copied or rehashed. No RF collection was started and QNAP paths were not modified. This snapshot is not an atomic view of ongoing capture activity.

Eight tests pass for acquisition-time boundaries, duplicate identity handling, sample-rate extraction, immutable prior membership and stable labels, including late-discovered earlier recordings. All sealed file hashes and the compressed manifest were independently verified.

## Reproduction

Use the pinned [freeze tool](dataset/freeze_ds28.py) and its [support adapters](dataset/support), with the modern analysis environment at `/srv/bulk/leo-dev/fast-algo02-production-v1`. The inputs are DS27 revision 1 as `--parent`, DS28 revision 1 as `--previous`, `--dataset-id DS28`, and `--cutoff-ns 1793543987024292987`. Set `PYTHONPATH=src:tools`, disable bytecode writes, and choose a new output directory; the tool refuses to overwrite an existing manifest. Historical file permissions require read access equivalent to the recorded census. Run [the tests](dataset/test_freeze_ds28.py) with pytest.
