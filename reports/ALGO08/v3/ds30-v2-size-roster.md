# Whole DS30 size screen using released ALGO08v2 outcomes

The full local ALGO08 regional-release replay covers all **455 physical DS30 recordings** and both calibration arms. It supplies **439 evidence-checked fixes**, 15 withholds and one solver failure. All **14 recordings below 500 MB** withheld in both arms. The smallest fixed recording remains DS30-0016 at **991,734,597 compressed bytes**, followed by DS30-0049 at **1,202,056,196 bytes**. This screen found no new positive with a documented complete resident copy or within the size cap. [Released regional replay](../regional-release/README.md) · [All 910 arm rows](../regional-release/ds30-replay.csv) · [Machine roster](measurements/ds30-v2-size-roster.json.gz)

The join matched DS30 labels to the original signed membership, summed each recording's original compressed payload sizes, and checked every member's issued count and observed extent against that metadata. The ranking uses compressed bytes, then issued visits, then label. Only each release arm's decision and evidence-check flag enter enrollment. Every v2 decision agreed with the earlier full study's compact fix flag across the 910 rows. The regional replay used authenticated saved two-scan detections, which supports enrollment. A named ALGO08v3 full-run comparator and current acquisition custody are separate requirements. [Sealed physical membership](../../2026_11_20_ds30_fast/dataset/manifest.sha256) · [Full compact comparison](../../2026_11_21_ds30_full/paired.csv)

| Shortest v2 positives by original payload | Compressed bytes | Issued | Members / segments | Historical payload pages resident |
|---|---:|---:|---:|---:|
| DS30-0016 | 991,734,597 | 808 | 13 / 2 | 0 / 242,128 |
| DS30-0049 | 1,202,056,196 | 986 | 16 / 2 | 0 / 293,479 |
| DS30-0238 | 1,511,312,978 | 1,242 | 20 / 3 | 0 / 368,984 |
| DS30-0191 | 1,514,118,459 | 1,230 | 20 / 3 | 0 / 369,668 |
| DS30-0309 | 1,734,131,479 | 1,408 | 22 / 3 | 0 / 423,384 |
| DS30-0115 | 1,770,740,055 | 1,465 | 23 / 3 | 0 / 432,321 |
| DS30-0161 | 1,773,983,982 | 1,423 | 23 / 3 | 0 / 433,114 |
| DS30-0058 | 1,921,944,447 | 1,562 | 25 / 4 | 0 / 469,239 |

These eight are the entire positive roster below 2 GB. Sorting first by issued visits swaps DS30-0191 ahead of DS30-0238 and DS30-0161 ahead of DS30-0115. The previous metadata-only residency receipt covered every recording from 100 through 2,000 issued visits. It recorded zero cached payload and index pages for these eight on that observation. The next recording after the sub-500 MB group, DS30-0340, used 686,440,127 bytes and failed the v2 solver in both arms. All eight positives above preserve every recorded original member, and the recorder marked their captures interrupted. Among recorder-complete positives, the minimum compressed extent was **8,119,652,186 bytes** on DS30-0275 with 6,773 issued visits. [Passive residency receipt](measurements/small-raw-passive-residency.json.gz) · [Full ranked roster](measurements/ds30-v2-size-roster.json.gz)

## Existing comparison and custody

The independently pinned 100-case ALGO08v3 publication panel contains none of those eight positive recordings. Its smallest positive is DS30-0057 at 3,346,554,376 bytes and 2,717 visits. DS30-0016 has a separate genuine named-v3 raw pair on its original offer and TLEs, but the later survey recovered only one complete local member and part of the next. DS30-0049 and DS30-0238 have authenticated original replay request metadata, original-region identifiers, and causally eligible archives with 48 and 49 signed snapshot names, respectively. Neither has a locally documented exact named-v3 complete pair. DS30-0191 has a 51-snapshot causal request and a sealed clock-only packet, with no authentic named-v3 detector packet located in its earlier targeted census. [Named panel method](prospective-small-physical.md) · [DS30-0016 named pair](raw-0016-best.md) · [Alternate-file survey](alternate-physical-source.md) · [DS30-0191 preflight](select-before-cfo-0191-preflight.md)

DS30-0238 is the next positive by bytes beyond the two established small cases. Its compact-era binding and request hashes cross-check against the same ordered three original segment manifests, with 1,231 admitted visits and 37 distinct causal catalogue bodies strictly preceding the original cutoff. No authenticated complete resident copy, exact named-v3 counterpart or already staged complete TLE archive for that case is established by the reviewed receipts. It exceeds the byte cap by more than 1 GB. [Manifest and request custody](measurements/ds30-v2-size-roster.json.gz)

This is a local report and pinned-metadata join. No waveform or catalogue body was opened, no original backing directory was walked, and no evaluation or new residency probe ran. The uncompressed machine receipt SHA-256 is `f6849fcc5548e8ea753ce7883f5f5e1f1bd5edb77bda941f31511424d793cd22`. [Receipt](measurements/ds30-v2-size-roster.json.gz)
