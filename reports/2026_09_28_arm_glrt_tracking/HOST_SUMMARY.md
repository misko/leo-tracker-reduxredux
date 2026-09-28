# Host tracking cohort summary

These are saved-IQ host measurements from the qualified x86-64 binary. They
are quality evidence and host CPU measurements, not ARM timing results. No RF
collection or hardware execution was performed for this archive.

## All 704 sealed dwells, refresh interval 2

All 704 manifest contexts are unique and present exactly once. Every dwell has
22 successful receiver/windows, eight candidates per window, and one native
summary whose CPU, GLRT attempts, and mode counts reconcile with its windows.
The fixed sealed denominator is 19,581 positive candidates in 7,007 positive
windows.

| Rate | Dwells | Candidate hits | Positive windows | Added candidates | Host CPU s/dwell |
|---:|---:|---:|---:|---:|---:|
| 2.5 MS/s | 152 | 3,898/4,573 (85.2%) | 1,548/1,682 (92.0%) | 677 | 0.559 |
| 5 MS/s | 216 | 4,828/5,466 (88.3%) | 1,770/1,874 (94.5%) | 684 | 1.430 |
| 7.5 MS/s | 184 | 4,539/5,186 (87.5%) | 1,780/1,933 (92.1%) | 652 | 2.575 |
| 10 MS/s | 152 | 3,811/4,356 (87.5%) | 1,424/1,518 (93.8%) | 584 | 4.044 |
| **All rates** | **704** | **17,076/19,581 (87.2%)** | **6,522/7,007 (93.1%)** | **2,597** | **2.106** |

Matches use maximum-cardinality one-to-one assignment within two samples and
8 kHz. Added positives are native positives without a sealed-baseline match;
they are not credited as recovered evidence.

## Metadata-balanced 64-dwell interval sweep

This smaller cohort contains eight lower-edge and eight upper-edge dwells at
each of the four rates. Its fixed denominator is 1,669 positive candidates in
691 positive windows.

| Refresh interval | Candidate hits | Positive windows | Added candidates | Host CPU s/dwell |
|---:|---:|---:|---:|---:|
| 1 | 1,669/1,669 (100%) | 691/691 (100%) | 0 | 3.773 |
| 2 | 1,444/1,669 (86.5%) | 634/691 (91.8%) | 254 | 2.049 |
| 3 | 1,298/1,669 (77.8%) | 587/691 (84.9%) | 387 | 1.399 |
| 5 | 1,206/1,669 (72.3%) | 574/691 (83.1%) | 482 | 1.129 |
| 11 | 1,072/1,669 (64.2%) | 523/691 (75.7%) | 623 | 0.403 |

`HOST_SUMMARY.json` contains the independently recomputed totals and per-rate
breakdown. `host-results/` retains gzip-compressed raw result rows, run
manifests, the executed evaluator snapshot, native source snapshots, the build
receipt, and hashes of both compressed and original row streams. The 704-dwell
result supports the interval-2 quality estimate across all rates; the interval
sweep is a smaller comparison and should not be read as a large-cohort estimate
for intervals 1, 3, 5, or 11.
