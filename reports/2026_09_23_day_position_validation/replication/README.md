# Disjoint day replication of the conditional joint-position method

The frozen method did **not** reproduce the earlier 314 m result. Across seven new,
nonoverlapping 16-scan blocks, its median error was 4.321 km, its range was
1.168–10.734 km, and none of the seven estimates was within 300 m. The separate final
four-scan partial block had 1.937 km error. This empirical distribution does not support
a repeatable 300 m accuracy claim.

| Group | Scans | Tracks | Observations | Joint error km | Mean Sacramento km | Mean Reno km |
|---|---:|---:|---:|---:|---:|---:|
| block 01 | 16 | 578 | 15,730 | 2.364 | 3.779 | 2.845 |
| block 02 | 16 | 599 | 14,884 | 1.542 | 2.584 | 4.300 |
| block 03 | 16 | 514 | 12,560 | 7.541 | 4.468 | 28.597 |
| block 04 | 16 | 496 | 12,786 | 4.321 | 11.769 | 108.529 |
| block 05 | 16 | 497 | 12,467 | 10.734 | 5.876 | 48.530 |
| block 06 | 16 | 461 | 13,081 | 1.168 | 8.849 | 13.389 |
| block 07 | 16 | 460 | 12,380 | 4.902 | 14.444 | 86.444 |
| block 08, partial | 4 | 136 | 4,194 | 1.937 | 5.321 | 180.701 |

The inventory was frozen before these fits. It spans 2026-09-22 15:15 through
2026-09-23 15:15 UTC, excludes all original development scans, and partitions every
eligible scan chronologically into seven complete groups plus one partial group. Block
04 spans a gap caused by removed development scans; none of the groups represents
continuous IQ.

Every group independently repeats the original conditional method: exact production
randomized masks, causal TLEs, qualified first-sample epochs, a per-scan union of all
Sacramento/Reno selected identities, integer timing offsets from -5 to +5 seconds, and
at most 35 Nelder-Mead evaluations per retained basin. Seeds come only from that
group's own production selected/finest coordinates. The known receiver coordinate is
introduced only after inference to calculate error. The two mean controls likewise use
only the block's production estimates before evaluation.

This remains a production-shortlist replication. The production evaluation rows had
already participated in identity and position selection, so these are conditional
selection results rather than a fresh held-out frequency test. The separate
full-catalogue frozen-position analysis is required for that stricter question.

The run processed 3,741 tracks and 98,082 observations in 490.9 seconds with two
workers. A post-run audit matched every cached track-evidence digest and both source
manifest digests to the frozen inventory.

Reproduction from the repository root:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  .venv/bin/python tools/research/day_position_replication.py \
  --inventory reports/2026_09_23_day_position_validation/inventory.json \
  --output reports/2026_09_23_day_position_validation/replication \
  --budget-seconds 900 --workers 2
```

`results.json` contains the aggregate distribution. Each block directory contains its
frozen session list, evidence/state cache, retained spatial basins, accumulation
sensitivity, and block result. `replication.png` compares the three methods by group.
