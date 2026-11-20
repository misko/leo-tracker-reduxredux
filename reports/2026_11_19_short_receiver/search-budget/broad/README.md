# First-ranked compact v5 on the broad roof panel

All 39 attempted recordings produced a fix in both calibration arms, including
all 31 original rank disagreements. Compared with no-repair v5 on those same
39 recordings, the first-ranked candidate had lower median and P95 error in
both arms. Eight fixes had greater error by more than 1 m, including four
by more than 100 m. The other 96 recordings have explicit unmeasured candidate
entries in the 135-recording roster. [Per-recording scores](per-recording.csv)

The original noncompact v5 audit selected rank zero on 104 of 135 recordings.
It selected rank one on 26 and rank two on five. The broad replay covers all
31 nonzero ranks and eight agreement controls. The roster comes from the
original branch audit, the six prescheduled timing runs and three SHA-selected
agreement recordings. [Preregistration](PROTOCOL.md)

## Position accuracy

The table gives median, P95 and maximum position error in kilometers on the
same recordings. The complete replay cohort consists of 35 DS26 and four
DS29 recordings. The disagreement cohort includes 30 DS26 and one DS29
recordings. Both arms had identical fix coverage. [Distributions by cohort and dataset](summary.json)

| Cohort | Arm | First-ranked | Compact projector | No-repair v5 | Within 5 km, all three methods |
|---|---|---:|---:|---:|---:|
| All 39 replayed | `c0` | 0.871 / 3.413 / 5.519 | 0.958 / 4.587 / 7.269 | 0.918 / 4.587 / 7.269 | 37 |
| All 39 replayed | `fitted_c` | 0.869 / 3.549 / 5.752 | 0.954 / 4.568 / 6.858 | 0.917 / 4.568 / 6.858 | 37 |
| 31 original disagreements | `c0` | 0.873 / 4.277 / 5.519 | 0.982 / 5.518 / 7.269 | 0.982 / 5.518 / 7.269 | 29 |
| 31 original disagreements | `fitted_c` | 0.936 / 4.234 / 5.752 | 1.040 / 5.522 / 6.858 | 1.040 / 5.522 / 6.858 | 29 |

In each arm, 33 of 39 first-ranked fixes were at most 5% worse than no-repair
v5 and 34 were at most 10% worse. Compared with no-repair v5, error improved
by over 1 m in 21, stayed within 1 m in 10, and increased by over 1 m in eight.
Four increases exceeded 100 m. The largest increase was on DS26-0072 in both
arms, at 1.164 km with `c0` and 1.423 km with fitted `c`. Coordinates differed
by over 1 m from no-repair v5 on 29 recordings in each arm. Compared with
the compact projector, five recordings were more than 10% worse in each
arm and 28 coordinates differed by more than 1 m. The compact-projector
coordinate changes reached 3.570 km and 3.702 km in the two arms.

The first-ranked and compact-projector arms matched exactly on all eight
replayed original rank-zero controls, including their conditional RF RMS.
Across the 39 paired recordings, median conditional RMS for first-ranked,
compact projector and no-repair v5 was 71.63, 71.99 and 71.74 Hz with `c0`,
and 71.61, 71.91 and 71.56 Hz with fitted `c`. These are fit diagnostics on
the conditional support of each method. The coordinate errors above use the
independent reference. [Candidate positions](v5_first_ranked_broad.jsonl.gz) · [Stock positions](orbit_projector.jsonl.gz)

## Inputs and scope

The candidate refreshes the first cold-ranked branch, then runs through the
compact projector and the original conservative recovery, orbit-history, signed
correction and cavity decision. Each attempt begins at the complete archived
native GLRT detections, with the original single 25 km roof tile and causal
catalogue. It uses the standard replay runner and 600-second wall deadline.
Each worker is pinned to one CPU and runs one numerical thread. The broad
launch kept at most six workers active on CPU cores 2, 3, 4, 5, 8 and 9.

Thirty disagreement attempts and three agreement controls were launched for
this experiment. DS26-0036 uses its original six-pair run. Five other
agreement attempts come from that same timing roster. The SHA-selected
agreement controls are DS26-0201, DS26-0062 and DS26-0006. Candidate timings
for the six-pair cases live in a separate field from the 33 broad timings.
The paired stock timings come from the earlier compact-projector archive.
The 33 fresh workers took 63.93–254.31 s each, with a median of 100.65 s and
668.11 s elapsed from plan write through the final worker receipt. The six
earlier first-ranked runs had a 126.89 s median. The corresponding stock
archive median on all 39 inputs was 167.38 s. The archived runtimes are
from a separate campaign. [Prediction and provenance seal](receipt.json)

The compact-projector archive predates the optional initial-selection hook.
Its Python module has a different hash. The C kernel is identical. The six
fresh stock timing runs matched the historical archive exactly on their input
binding, endpoint coordinates, RF RMS and numerical work counters.
[Stock source and endpoint check](timing-stock-check.json)

The archive contains a compact projector fix for each of the 135 inputs. The
archived results lack a compact starting-node and gate record that would
prove equivalence between a first-ranked fit and the original selected
best-of-three fit. The remaining 96 agreement cases are unmeasured for the
candidate. A success count over the 39 attempted recordings describes the
measured cohort. It cannot be extrapolated to the 96 remaining recordings.

## Reproduction

The omitted `--work` and `--timing` arguments select the original replay
directories. Use `--work` to choose a different local directory and
`--timing` to identify the previously completed six-pair run directory.
Actual controls require access to the original native archive and frozen
numerical runtime. Run `--score` alone to verify and score the sealed files.

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python \
  -m tools.pipeline_eval.qualification.broad_search_budget --cpus 2 3 4 5 8 9
.venv/bin/python -m tools.pipeline_eval.qualification.broad_search_budget --seal --score
```
