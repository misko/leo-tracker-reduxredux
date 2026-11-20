# Compact roof complement completion

All eight supplement attempts completed within their original cap. Six produced both positions and two ended in numerical failures. Across the add-only 32-case complement, compact secant now has 22 fixes per arm, eight numerical failures, one timeout and one unavailable recording. Every eligible case was attempted. [Supplement outcomes](scores.csv) · [All 32 decisions](all32-positions.jsonl.gz)

This separate run schedules the eight eligible cases that had no launch in the original compact replay. The original prediction lock, original hash order and each case's exact prepared request were frozen before these launches. The first 23 attempts and the frozen unavailable case retain their earlier outcomes. The supplement uses the same compact secant source, original five initial phase rounds, original matched tile and 195-second worker cap. [Eight-case roster](roster.json) · [Original bounded experiment](../compact/README.md)

Eight independent workers ran with nice +10 on CPUs 0, 2, 3, 6, 8, 9, 12 and 16. The new rows preserve actual timeouts and numerical failures. The separate all-32 archive changes only the eight previously unlaunched cases. [Eight-case prediction lock](prediction-lock.json) · [Add-only full complement seal](all32-prediction-lock.json)

| Cohort | Fixes per arm | `c = 0` median / P95 (km) | Fitted `c` median / P95 (km) | Median conditional RMS, `c = 0` / fitted `c` (Hz) |
|---|---:|---:|---:|---:|
| Supplemental cases | 6 of 8 | 1.113 / 2.029 | 1.069 / 2.006 | 64.238 / 64.220 |
| Full compact complement | 22 of 32 | 1.062 / 4.859 | 1.156 / 4.824 | 66.954 / 66.910 |

The two new failures were an orbital interpolation error on DS26-0156 and an assertion on DS26-0285. The longest new worker took 126.73 s. Across the full complement, original no-repair v5 published 16 fixes per arm. Compact and original no-repair share 15 fixes, with median paired compact-minus-original geographic differences of +0.49 m and +0.58 m. Compact published seven additional cases. Original no-repair alone published DS26-0217, which reached the cap in the initial compact run. [Verified original role outcomes](../compact/original-roles.json) · [Supplement score seal](score-lock.json) · [Eight-case chart descriptor](figures.json)

## Reproduce

Use the original compact run's local workspace, which holds the authenticated prepared request inputs. Prepare locks the new roster and starts the supplement's 400-second wall window. Run each assigned core once.

```bash
completion=/tmp/compact-roof-completion
original=/tmp/compact-roof-complement
nice -n 10 .venv/bin/python -B -m tools.pipeline_eval.qualification.compact_roof_completion \
  prepare --work "$completion" --original-work "$original" --out "$completion/report"
for cpu in 0 2 3 6 8 9 12 16; do
  nice -n 10 taskset -c "$cpu" .venv/bin/python -B \
    -m tools.pipeline_eval.qualification.compact_roof_completion run \
    --cpu "$cpu" --work "$completion" &
done
wait
.venv/bin/python -B -m tools.pipeline_eval.qualification.compact_roof_completion \
  publish --work "$completion" --out "$completion/report"
.venv/bin/python -B -m tools.pipeline_eval.qualification.compact_roof_selection_results \
  score --out "$completion/report"
```
