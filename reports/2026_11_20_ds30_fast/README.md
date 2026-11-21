# DS30 fast recordings and blind Gauss replay

DS30 revision 1 covers whole fast acquisitions from **November 13, 2026 at 04:55:00 UTC, inclusive, through November 20, 2026 at 23:37:05 UTC, exclusive**. DS29 revision 1 ends at the same lower boundary. Each acquisition belongs to a dataset according to its earliest segment. Copies share a single raw-content identity.

The census found **455 fast acquisition directories** across 25 storage roots. It checked 29,423 manifests and identified 364 adaptive manifests outside the requested recording format. Gauss had 446 of the fast acquisitions on bulk storage and nine on the NVMe spool. The automatic acquisition ledger independently named the same 455 recordings. [Discovery census](dataset/discovery.json) · [Ledger reconciliation](dataset/ledger.json)

All 455 acquisitions used 10 MS/s. There are **411 complete recordings and 44 incomplete recordings**. Of the complete recordings, 387 have a published tracking input and 24 lack one. The 44 incomplete recordings also lack a published tracking input. The corpus contains 2,878,757 windows in 45,080 chunks, totaling 3,521,160,723,188 compressed bytes. The index and payload-size checks reported zero integrity errors.

| Acquisition date, UTC | Recordings | Complete | With a published tracking input |
|---|---:|---:|---:|
| November 13 | 44 | 43 | 42 |
| November 14 | 62 | 53 | 53 |
| November 15 | 57 | 52 | 52 |
| November 16 | 60 | 52 | 52 |
| November 17 | 61 | 55 | 55 |
| November 18 | 62 | 52 | 50 |
| November 19 | 57 | 54 | 50 |
| November 20 | 52 | 50 | 33 |
| **Total** | **455** | **411** | **387** |

The compressed manifest binds acquisition metadata, chunk and index digests, payload lengths, and available native timing contracts. The raw I/Q stays in the recording archive. The freezer checks chunk indexes and payload lengths across the dataset. Each blind replay also verifies its individual I/Q windows. [Full manifest](dataset/manifest.json.gz) · [Membership summary](dataset/membership-summary.json) · [Evaluation units](dataset/evaluation-units.json) · [Verification](dataset/verification.json)

The first acquisition began at 05:00:57 UTC on November 13 and the last at 23:23:26 UTC on November 20. All 455 content identities are unique and there is zero overlap with DS29. The uncompressed manifest SHA-256 is `a4ce879975be0593f1adeb7c106f31660c6c423f17e2c7858985244530dc0eb8`.


List this release with `leo datasets list --dataset DS30 --json`.
