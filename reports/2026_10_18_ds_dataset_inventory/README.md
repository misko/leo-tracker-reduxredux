# DS dataset inventory and creation-date evidence

Located **20 named datasets**, plus the separately frozen **DS2-22** revision. The table records creation/mint timestamps where available, then inventory completion/observation dates where creation was not explicitly timestamped. A capture cutoff is labeled separately and is **not** an authenticated creation time.

Known timestamps are converted to **America/Los_Angeles (PDT, UTC−7)**. This explains why some dates differ from UTC-dated report directories. DS1 and DS2-22 have only a dated report label in the inspected authority; their exact creation time and original timezone are unrecorded.

| Dataset | Date (PDT unless noted) | Date evidence | Recordings | Scope |
|---|---|---|---:|---|
| DS1 | 2026-09-24* | Dated report; exact creation unknown | 339 | Frozen multi-duration regression benchmark; original captures precede naming |
| DS2 | 2026-09-24 | Inventory observed | 20 | Original whole-recording corpus |
| DS2-22 | 2026-09-24* | Dated report; exact creation unknown | 22 | Revision preserving DS2's 20 recordings and adding two |
| DS3 | 2026-09-24 | Inventory observed | 56 | All qualified captures through its frozen cutoff |
| DS4 | 2026-09-25 | Inventory observed | 91 | Post-DS3 captures |
| DS5 | 2026-09-26 | Inventory observed | 42 | Recordings since local midnight |
| DS6 | 2026-09-26 | Explicit mint timestamp | 43 | Roof recordings with pose evidence |
| DS7 | 2026-09-27 | Inventory completed | 88 | Complete post-DS6 recordings |
| DS8 | 2026-09-27 | Explicit mint timestamp | 65 | Complete post-DS7 recordings |
| DS9 | 2026-09-28 | Inventory completed | 105 | Post-DS8 recordings with complete analysis at freeze |
| DS10 | 2026-09-29 | Inventory completed | 187 | Post-DS9 recordings with complete analysis at freeze |
| DS11 | 2026-09-29 | Inventory completed | 87 | Complete post-DS10 recordings |
| DS12 | 2026-09-30 | Inventory completed | 160 | All sealed post-DS11 recordings, including unpublished archives |
| DS13 | 2026-10-02 | Inventory completed | 17 | Analysis-complete scans starting at `scan-fw-911c4e5db9243281` |
| DS16 | 2026-10-07 | Explicit creation timestamp | 63 | Published recordings in the frozen 16-hour window; 48-recording evaluation is a subset |
| DS17 | 2026-10-08 | Inventory completed | 51 | Whole post-DS16 recordings |
| DS18 | 2026-10-08 | Inventory completed | 34 | Sealed post-DS17 recordings, including one firmware archive |
| DS20 | 2026-10-11** | Inventory cutoff only | 18 | Eight-channel GLRT-qualified fast recordings |
| DS21 | 2026-10-12** | Inventory cutoff only | 108 | Post-DS20: 54 fast and 54 adaptive |
| DS22 | 2026-10-14** | Inventory cutoff only | 137 | Post-DS21: 69 fast and 68 adaptive |
| DSX01 | 2026-10-16 | Explicit creation timestamp | 5 | Five fast scans; 15 selected challenge windows and 20,084 whole-scan GLRT observations |

`*` Report-label date; timezone and actual creation instant were not recorded. DS1 names an existing historical cohort rather than newly collecting those recordings that day.

`**` The frozen acquisition-start cutoff is available, but the actual mint timestamp is absent from the inspected authority. These dates identify the freeze boundary; creation occurred at or after that boundary.

**DS14, DS15 and DS19 were not located** in the checked sources. This is not proof that they were never created. No additional named DS23+ or DSX02+ membership authority was found in this bounded search.

## Source and date evidence

[inventory.json](inventory.json) contains every exact UTC/PDT timestamp, the field used, the source locator and a content binding. Legacy authorities were read from Git commit `75b76f66974c78588c6599822e8007aaa767466b`. Recent manifests were read from the current workspace and the original DS16/DS20 worktrees. Large modern manifests are bound here by file size plus a SHA-256 of their first 65,536 bytes, which contain the timestamp fields; this is explicitly not a fresh full-manifest or raw-IQ integrity seal.

The starting index is `docs/research/datasets.md`. Additional checks covered accessible Git objects and `origin/main`, sibling and registered worktrees, and bounded report-directory searches beneath development archives. Some metadata snapshots remain local or Git-ignored; their source locators in the JSON identify the exact local authority. Missing index entries were not interpreted as missing recordings.

Explicit creation timestamps found:

| Dataset | Creation/mint UTC | Corresponding PDT |
|---|---|---|
| DS6 | 2026-09-27 06:00:43 | 2026-09-26 23:00:43 |
| DS8 | 2026-09-28 00:24:44 | 2026-09-27 17:24:44 |
| DS16 | 2026-10-08 01:37:32 | 2026-10-07 18:37:32 |
| DSX01 | 2026-10-16 23:46:52 | 2026-10-16 16:46:52 |

## Interpretation

These are membership counts, not counts of independent scientific replicates. Datasets overlap: DS2-22 is within DS3, and DSX01 is a retrospective challenge drawn from an existing recording corpus. Combined DS7–DS10 studies, receiver-confirmation subsets and later DSX01 analysis reports are derived views rather than newly minted dataset IDs. Deduplicate recording/session/content identities before combining memberships.

This inventory used metadata only. No RF was collected, no source recording was changed, and no payload integrity revalidation or analysis-readiness campaign was performed.
