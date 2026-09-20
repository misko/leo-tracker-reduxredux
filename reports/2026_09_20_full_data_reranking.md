# Full-observation catalogue reranking does not resolve the recent bias

Reranking the full catalogue with every fitting observation changes only **3 of
622** retained satellite assignments. All **190** tracks in the frozen quality
selection keep their original identities. Refitting those same selected tracks
reproduces the previous 4,582.8 m fixed-clock and 3,887.7 m shared-clock errors.

## Experiment

The independent 9,000-mile-wide search used at most six randomized fitting and
six evaluation observations per source to make the global search affordable.
This audit removes that cap (`--max-per-partition 0`) at the continuous
**all-data, fixed-recorded-UTC** position from the completed blind inference.
That starting model was chosen by its definition, not its distance from the
antenna. The full original causal catalogues are reconsidered at this location;
no known position or previous NORAD shortlist is supplied.

The same scoring and eligibility rules retain 630 tracks, comprising all
previous 622 plus eight newly passing tracks. To separate assignment changes
from cohort changes, a second comparison keeps exactly the original 622 tracks
and original 190-track selection and changes only the reranked identities.
Randomized evaluation observations do not select the candidates or fit position.

| Matched cohort | Clock treatment | Original error (m) | After reranking (m) | Evaluation RMS after (Hz) |
|---|---|---:|---:|---:|
| All 622 tracks | Fixed UTC | 4,800.8 | 4,865.4 | 166.84 |
| All 622 tracks | Shared ±0.5 s | 3,805.0 | 3,863.9 | 164.04 |
| Original selected 190 | Fixed UTC | 4,582.8 | 4,582.8 | 85.91 |
| Original selected 190 | Shared ±0.5 s | 3,887.7 | 3,887.7 | 85.15 |

| Recording | Previous NORAD | Full-fitting-data NORAD |
|---|---:|---:|
| `scan-fw-f5c5c846a92fc5e7` | 56546 | 66474 |
| `scan-fw-1be2dad4c21118c5` | 66886 | 59332 |
| `scan-fw-57a9b32fc950036e` | 63470 | 63946 |

Including all 630 newly retained tracks gives 4,831.3 m fixed-clock and 3,765.2 m
shared-clock errors. Reapplying the quality rule to that expanded cohort gives
4,652.6 m and 3,939.7 m respectively. These additional comparisons also fail the
sub-kilometre target; none is promoted as a corrected model.

This audit makes capped grid observations an unlikely explanation for the bias
in the selected cohort. It does **not** prove satellite identities: reranking is
conditional on the inferred location, and similar orbits can remain ambiguous.
It is one bounded reassignment experiment, not a proof of global convergence.

## Reproduction and evidence

Run `tools/study_adaptive_sky_position.py search` on the existing evidence export
with `--points proposal.json --max-per-partition 0 --clock-s 0`, then run
`tools/polish_randomized_wide_mode.py` on the new search output. Both are existing
tested research scripts; no inference algorithm or production setting changed.
The matched-cohort comparison uses the same `compare_positioning_cohorts.fit`
function with episode masks joined by `(session_id, episode_id)` to the original
assignments. This preserves 21,702 all-cohort and 7,156 selected observations.

- [Location proposal and parent digest](2026_09_20_full_data_reranking/proposal.json)
- [Completed full-catalogue reranking result](2026_09_20_full_data_reranking/search-result.json)
- [Refits and new assignments](2026_09_20_full_data_reranking/inference.json)
- [Matched-cohort fits and exact assignment changes](2026_09_20_full_data_reranking/matched-cohort.json)
- [Source provenance](2026_09_20_full_data_reranking/inputs.json)

Reported errors are evaluated after inference against the user-supplied antenna
coordinate, with the same spherical distance convention as the parent report.
No new RF collection was performed.
