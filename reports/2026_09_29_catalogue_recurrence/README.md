# Cross-snapshot catalogue mapping restores raw donor coverage

**All 14 baseline rosters are resolved and independently audited across the
complete 258-scan corpus.** Raw candidate recurrence is much broader than the
previous same-snapshot subset suggested. This is useful coverage evidence for
a donor-transfer experiment, not verified association or geographic improvement.

The completed census contains **15,258 bank-eligible tracks** and **10,627
distinct physical catalogue numbers**. Of those catalogue candidates, 5,394
occur in at least three recordings; the maximum is ten recordings. A catalogue
number identifies a candidate object, not which object generated a track.

| Dataset | Frozen scans | Tracks | Tracks with a candidate in ≥2 earlier donor scans | Scans with supported tracks |
|---|---:|---:|---:|---:|
| DS7 | 88 | 5,131 | 3,356 (65.41%) | 61/88 |
| DS8 | 65 | 3,840 | 3,704 (96.46%) | 65/65 |
| DS9 | 105 | 6,287 | 6,237 (99.20%) | 105/105 |

Donors are strictly earlier recordings across the authorized datasets. The
counts are identical when donors must also be outside the target's fixed
chronological block of eight. These structural blocks are distinct from the
previously selected early/middle/late panels. The last block may be shorter.
Multiple tracks in one recording count as one donor scan.

Support here means **raw candidate-list overlap**, not agreement among favored
associations. Supported candidate slots are 9,981/66,975 for DS7,
10,590/49,496 for DS8 and 49,861/81,494 for DS9. The distinction matters:
a track can have one recurrent, low-probability alternative without its
favored candidate recurring. No full-corpus posterior weights are fabricated.

## Matched comparison on the original 72 scans

The previous 72-scan training distributions can now be joined by physical
catalogue number across snapshots. Strong donor membership still requires
signal responsibility × conditional candidate weight ≥0.5 in at least two
strictly earlier scans. All target tracks remain in the mass averages.

| Dataset | Target tracks | Mean conditional mass with strong two-donor support | Tracks with supported mass >0.5 |
|---|---:|---:|---:|
| DS7 | 1,434 | 0% | 0 |
| DS8 | 1,434 | 0% | 0 |
| DS9 | 1,460 | 0.4099% | 6 |

Requiring donors outside the original target panel leaves these results
unchanged. The earlier same-snapshot two-donor census was zero for all datasets;
the current mapped result adds six DS9 tracks above 0.5 supported mass. This is
still too sparse to justify a correction across all panels from those 72 scans
alone. The full 258-scan raw counts and these weighted 72-scan outcomes must not
be substituted for one another.

![Catalogue recurrence and weighted panel support](recurrence.png)

## How the mapping is established

Every original observation and candidate-bank byte hash was checked against
the full-ready authority. Exact baseline snapshot digests were resolved using
the existing read-only TleArchiveReader at its configured root. No archive
storage path was guessed, and no current provider product replaced an old one.

The exporter's STARLINK DEB exclusion was reproduced before parsing baseline
roster order. The public catalogue and record parsers agreed on every ordered
catalogue-number list. Counts and uniqueness matched all bank manifests.
Every bank row was range checked and explicitly mapped to a catalogue number.
The [rosters](rosters.json), compressed original snapshot bytes, and copies and
digests of imported runtime sources preserve this evidence. Replacing orbital
element sets in the original exporter preserves baseline catalogue ordering;
element revisions do not imply that orbit errors remain constant over time.

The independent raw-line audit initially rejected Alpha-5 fields such as
`A0001`. The failure and original audit source are preserved. The corrected
auditor uses explicit Alpha-5 decoding and matches all fourteen rosters,
including debris exclusions, without rerunning the scientific extraction.
[Audit correction and limits](AUDIT-CORRECTION.md).

## Verification and decision

Four prelaunch tests passed for mapping and chronological support. Three
additional audit-reader tests passed after the Alpha-5 issue was identified.
The mapping/census child exited zero in **9.01 s**, peak RSS **405,992 KiB**,
under a 120 s timeout and 4 GiB address-space limit. The independent auditor
reconstructed all **30,516 full-corpus target/scope rows** and **8,656 panel
target/scope rows**, verified raw snapshot hashes and mapped identities, and
checked all sealed source/input/process hashes. It is not an independent
radio-likelihood implementation or verification of physical signal identity.

No correction, geographic fit or new accuracy estimate was produced. No RF,
raw IQ, propagation, provider refresh, QNAP mutation or production change was
needed. Existing archive metadata was read through its port.

The next step is to measure **training-weighted donor support on the full
corpus**, using one consistent likelihood and keeping donor fitting separate
from target held evaluation. Raw overlap alone cannot choose a satellite
correction. Initially unsupported DS7 recordings must remain explicit rather
than receiving invented historical calibration. [Next experiment](NEXT.md).

[Complete tables](RESULTS.md), [summary](summary.json), [protocol](PROTOCOL.md),
[runtime provenance](runtime.json), [tests](tests.log), [audit tests](audit-tests.log),
[complete evidence hashes](evidence-sha256.json).
