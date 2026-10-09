# Iteration85: ablation from deployed bounded-recovery hard60

User-authorized full DS16/DS17/DS18 ablation; production unchanged. All148
members (63/51/34) and exposure labels are inherited from the frozen full-cohort
authority. These are consumed development recordings, not unseen validation.

| ID | Configuration | Main comparison |
|---|---|---|
| B0 | Archived deployed hard60 with bounded recovery | Baseline |
| B1 | B0 plus distinct sep25/sep50 regional finalists | B1−B0: search |
| B2 | B0 plus joint receiver-clock/position fitting | B2−B0: joint fit |
| B3 | B1 plus joint fitting | 2×2 search/joint interaction |
| C3 | B3 unpruned refit | Same-start compute control for B4 |
| B4 | B3 plus remove satellites with absolute relative timing >5s | B4−C3: pruning |
| C4 | B4 narrow receiver-clock-prior refit | Same-start control for B4W |
| B4W | B4 with receiver-clock prior scale2→4 | Separate clock-prior relaxation |
| C5 | B4W RF-time-off refit | Same-start control for B5 |
| B5 | B4W plus receiver RF-time coefficients, sigma50 | B5−C5: RF time |
| C6 | B5 model refit | Same-start control for satellite slopes |
| B6 | B5 plus satellite-slope sigma0.25 Hz/s | B6−C6 |
| B7 | B5 plus satellite-slope sigma0.5 Hz/s | B7−C6 and B7−B6 |

Every row has matched static c=0/fitted-c. RF-time coefficients are locked in
c=0, and also locked for fitted-c in RF-time-off configurations. Thus C5 isolates
static c while B5 versus C5 fitted-c isolates RF-time flexibility. Candidate banks,
calibration and shared seeds are fitted-derived: conditional matched ablation,
not independent end-to-end c-specific searches. Reference coordinates/errors
are read only for post-fit evaluation and reporting, never model selection.

B0/B1 reuse verified immutable production/regional receipts rather than claiming
a cold grid rerun. All downstream fits are fresh90s/600iteration attempts, using
two single-thread workers, unchanged independent0.001 convergence gate,25km local
radius,hard60,relative timing sigma2/common3 and existing spatial prior. We retain
all original regional finalists. Regional selection uses the original comparable
score; scores are never compared across changed models. Extra computation and
local recentering are disclosed, and C3/C4/C5/C6 provide same-start controls.

Each stage accepts its independently qualified result or keeps its prescribed
upstream fallback. Downstream shared initialization uses the first qualified
fitted-c prerequisite; missing prerequisites remain explicit not-attempted stages,
never omitted members. Pruning requires at least4 satellites. Every raw attempt,
fallback, failure and input failure is recorded. No per-scan best-error choice.

The initial ladder is frozen before execution. A subsequent frozen leave-one-out
study will remove components from the globally selected combination, after the
ladder comparison; it must not be represented as already performed. Independent
reserve evaluation and cold pipeline/shadow/PNG verification follow candidate
selection before any deployment. No reserve outcomes or new RF are consumed here.

Outputs must include full coverage/subgroups, per-dataset mean/median/p95/worst,
threshold counts, paired regressions, convergence/fallbacks, measured fit and
load time separately from archived regional compute, frequency RMS separate from
position accuracy, and position-error plots. The pending geometry-prior84 and
regional-recovery83 studies are separate and do not supply selective replacements.
