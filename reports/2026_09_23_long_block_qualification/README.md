# Older long-block input qualification

All six sampled recordings from the September 21 eight-hour groups are usable by
the current position-input model; the remaining recordings are not yet qualified.
This bounded qualification selected the first, middle (`floor(n/2)`), and last session
from each metadata-frozen group. Selection used no track or position outcome.

| UTC group | Source scans | Sampled scans ready | Eligible ≥3 s tracks | Observations | Train / reserved rows |
|---|---:|---:|---:|---:|---:|
| 2026-09-21 00:00 | 72 | 3 / 3 | 168 | 3,796 | 2,208 / 1,588 |
| 2026-09-21 08:00 | 80 | 3 / 3 | 111 | 3,733 | 2,189 / 1,544 |
| **Total** | **152** | **6 / 6** | **279** | **7,529** | **4,397 / 3,132** |

Every sampled scan loaded through `ScannerTrackingInputStore` and completed
`prepare_adaptive_tle_position_inputs` against the read-only `TleArchiveReader`.
Thus no legacy fallback or radio re-analysis is needed for an initial position study.
Each scan has a causal TLE snapshot with 10,695–11,114 usable candidates, and the
prepared UTC origin exactly equals the saved first-sample timing authority.

The sampled captures are consistently 2.5 MHz `scan-hop` recordings from
`radio_pluto_19f2`, with receiver IDs 0 and 1 and channels 1–4. First-sample UTC
brackets span 1.19–1.52 ms and are qualified under the host-bracketed device-counter
authority. Actual sampled RF support varies by scan from four to eight frequencies in
the 10.710–11.690 GHz range; downstream comparisons must preserve each scan's saved
frequency normalization rather than assume identical channel coverage.

Eligible track counts vary from 27 to 93 per sampled scan. Median track spans range
from 13.3 to 21.3 seconds, and maxima range from 38.2 to 54.7 seconds. This is adequate
for the existing ≥3 s track model and provides substantially longer elapsed blocks.
The 00:00 group has a maximum inter-capture gap of 1,152.6 seconds, while the 08:00
group's maximum is 361.8 seconds. Report summed capture duration and elapsed span
separately; the first group is not a continuous eight-hour observation.

`qualification.json` records every selected ID, exact input/analysis/raw authority
digest, timing fields, receiver/channel coverage, track accounting, randomized mask
counts, trajectory/evidence digest, and causal catalogue snapshot. This six-scan
sample qualifies the format and adapters, not all 152 recordings. Before a full long
fit, freeze the complete group IDs and run the same lightweight preparation/accounting
check over each group; no new RF collection or full spatial search is required for
that gate.

Reproduce the bounded check with:

```bash
.venv/bin/python reports/2026_09_23_long_block_qualification/qualify.py \
  --inventory reports/2026_09_23_long_group_metadata/inventory.json \
  --output <fresh-output-directory>
```

The script accesses storage only through public read-only adapters in a `leo` user
subprocess and writes the report as the invoking user.
