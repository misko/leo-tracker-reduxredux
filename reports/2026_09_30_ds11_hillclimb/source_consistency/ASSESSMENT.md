# Training-source-consistent screen assessment

Later [probe semantics](../probe_overlap_semantics/README.md) and
[waveform coexistence](../probe_coexistence/README.md) evidence supersedes the
interpretation of shared probes as necessarily conflicting observations.
The frozen deletion results below stand; shared provenance alone does not prove
duplicates or mutual exclusivity.

The source provenance issue is substantial on the fixed screen: 2,221 training
source groups occur across multiple exported tracks, involving 4,487 of 16,016
training observations (28.02%). The frozen training-only selector retains
12,052 training observations (75.25%) in 356 of 489 tracks. Per-scan retained
training coverage is 70.03--80.84%.

The single `training_source_consistent` arm does not pass its predeclared screen
gate. All eight processes and endpoints qualify, but it has only four paired
wins and worsens median position error by 13.06%.

| metric | source-consistent | original IID |
|---|---:|---:|
| qualified / attempts | 8 / 8 | 8 / 8 |
| median error | 3514.231 m | 3108.162 m |
| mean error | 3605.878 m | 3481.538 m |
| P90 error | 5962.703 m | 6046.037 m |
| maximum error | 6171.641 m | 6345.775 m |
| paired wins | 4 | -- |
| sub-kilometre results | 0 | 1 |

| index | retained tracks | training retained | subset error (m) | IID error (m) |
|---:|---:|---:|---:|---:|
| 0 | 47 / 62 | 78.30% | 1275.702 | 765.072 |
| 4 | 43 / 61 | 73.32% | 3366.606 | 3510.342 |
| 8 | 44 / 61 | 75.60% | 4993.322 | 5270.648 |
| 12 | 40 / 59 | 70.03% | 1453.276 | 1183.767 |
| 16 | 41 / 58 | 73.88% | 3661.856 | 2153.140 |
| 20 | 46 / 63 | 75.38% | 2051.462 | 2705.981 |
| 24 | 50 / 64 | 80.84% | 6171.641 | 5917.578 |
| 28 | 45 / 61 | 76.06% | 5873.159 | 6345.775 |

The common all-track IID held-score diagnostic at the subset endpoints sums to
+3.940 nats, with mixed per-scan signs. Native subset likelihood is not compared
with the all-track model because the dimensions differ. The geographic screen
failure is sufficient to stop this hard-selection family without replication.

The result does not make independent treatment of conflicting raw sources
scientifically correct. It shows that deterministic maximum-coverage deletion
loses useful constraints along with conflicting alternatives and does not
improve DS11 single-scan localization. An explicit same-observation alternative
hypothesis model would need a dimension-matched likelihood before further work.
