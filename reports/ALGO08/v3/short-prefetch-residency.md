# The isolated full-short read-ahead comparison was blocked by source residency

No authorized recording had three consecutive complete members with both payload and index pages resident. The exact DS30-0008 fixture retained the first member and only **two pages** of the second. The two authorized alternates, DS30-0057 and DS30-0016, had no resident compressed payload pages at preflight. No payload was copied, no cache was evicted and no new benchmark ran. [Read-only observations](measurements/short-prefetch-residency.json.gz)

| Case checked | Members inspected | Resident payload pages | Fully resident payload-and-index members | Available adjacent triples |
|---|---:|---:|---:|---:|
| DS30-0008, exact first three | 3 | 18,909 / 56,663 | 1 | 0 |
| DS30-0057, complete recording inventory | 43 | 0 / 817,049 | 0 | 0 |
| DS30-0016, complete recording inventory | 13 | 0 / 242,128 | 0 | 0 |

The dense first member's payload and index were wholly resident. Its second and third indexes were nonresident. The probe used descriptor metadata and the pinned read-only cache observer under the capture account. Only authenticated manifests were opened as data. The bounded scratch search found the earlier signed detection outputs but no private copies of the exact compressed members. A remaining private XFS three-member fixture contained generated data and a different manifest. Host-wide I/O pressure in the recorded preflight was **11.87% full** over ten seconds and **21.66%** over a minute. These observations are instantaneous admission evidence, without a measured future cache condition. [Preflight source](short_prefetch_residency.py)

## What the archived comparisons already measure

The prior registered **physical XFS** comparison used the same exact 192-visit DS30-0008 prefix, the genuine 20/12 ms all-visit receiver, 48 full and 336 short lane calls, and identical signed detections. Its alternate changed both compressed read-ahead and the decoded arena. That leaves the isolated read-ahead effect unresolved.

| Physical XFS pair order | Path | Acquisition CPU / elapsed s | Compressed MB/s through acquisition | Elapsed less CPU ms | Peak RSS MiB | Process read bytes |
|---|---|---:|---:|---:|---:|---:|
| 1, first | Released next-member hints | 0.890 / 1.072 | 216.49 | 182.30 | 405.4 | 232,099,840 |
| 1, second | Whole-member prefetch and arena | 0.856 / 1.180 | 196.73 | 323.73 | 497.7 | 232,091,648 |
| 2, first | Whole-member prefetch and arena | 0.875 / 1.017 | 228.27 | 141.47 | 497.5 | 232,091,648 |
| 2, second | Released next-member hints | 0.921 / 1.062 | 218.57 | 141.17 | 405.8 | 232,091,648 |

All four historical runs began with zero private compressed pages resident. All original compressed, index and decoded authorities passed. Each prefetch arm's one CPU 2 worker read **154,640,914 bytes** from the two future members, with no misses. The process CPU includes **45.28 / 45.93 ms** of worker CPU. The demand wait moved from **324.53 ms** in one pair to **0.016 ms** in the other. The decoded arena and compressed worker both contribute to the observed stage and memory changes. The elapsed-minus-CPU span also includes scheduling and other uncharged time. Its value cannot be assigned wholly to device service. The durable seal is outside the table. [Same-aperture XFS comparison](full-short-arena.md) · [Complete historical receipt](measurements/full-short-arena.json.gz)

An older **prefetch-only XFS** comparison changed the bounded worker while retaining the released decoder. It paid native search on only 64 of 192 stereo visits. All arms authenticated the remaining visits and charged **232,091,648** physical-accounting bytes. The candidate sped up acquisition by **113.76 ms** in one order and slowed it by **1.72 ms** in the reverse order. The measured worker CPU was 50.09–51.50 ms and included in total process CPU. Those clocks answer the lower detector-duty case. The requested same-aperture, same-decoder, read-ahead-only result remains unmeasured. [Prefetch-only sparse comparison](sparse-cold-input.md)

## Reproduce the admission check

From a research checkout with the already installed cache observer and frozen release, run the metadata check under the capture account. Two focused tests passed, covering complete consecutive membership and independent index and payload residency.

```bash
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
sudo -n -u leo env PYTHONPATH="$PWD:$release/src:$release" PYTHONDONTWRITEBYTECODE=1 \
  "$release/venv/bin/python" -BPs -m reports.ALGO08.v3.short_prefetch_residency
```
