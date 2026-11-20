# RF preflight for late v5 recovery

An RF-only guard bypassed 16 of 135 original late reassociation calls and preserved all 270 archived arm endpoints. Both material geographic improvements after the cavity survived. The guard retained both original admissions, including the sole repair that changed the final position. The 133-record held split contained one admission and zero selected repairs. [Archive-stage charts for both arms](charts/index.html), [counts and distributions](summary.json).

The guard reads the native cavity fit’s per-track profile offset and conditional residual RMS. It requires two common tracks and at least 30 points in each calibration arm. A family passes when its mean offset has the same sign in both arms, reaches three standard errors across tracks, and reaches three quarters of the pooled per-track RMS. Any passing family leaves the original ranking and final reassociation intact. The original residual-addition branch always runs, and a bypass keeps its checked incumbent. The inputs are RF features only. [Frozen protocol](PROTOCOL.md), [predecision and source seal](predecision-lock.json), [sealed figure evidence](roof-lock.json).

## Where late recovery mattered

Original v5 altered both arm coordinates on 12 recordings after the cavity. Eleven changed at residual addition, and one changed at final identity reassociation. Three recordings moved at least 0.1 km. DS26-0239 moved roughly 0.33 km after its addition and its geographic error increased about 0.05 km in both arms. Only DS26-0066 and DS26-0287 improved by at least 0.1 km. The other nine additions changed the endpoint by less than 0.1 km. [Per-arm geographical scores](scores.csv).

| Recording and arm | Cavity error, km | After addition, km | Final and preflight replay, km |
| --- | ---: | ---: | ---: |
| DS26-0066 `c=0` | 2.389 | 2.389 | 1.244 |
| DS26-0066 fitted `c` | 2.370 | 2.370 | 1.218 |
| DS26-0287 `c=0` | 0.773 | 0.503 | 0.503 |
| DS26-0287 fitted `c` | 0.689 | 0.440 | 0.440 |

DS26-0066 retained the full reassociation and changed its final identity from 62025 to 68047. Two other families triggered the preflight on that recording. The guard therefore shows promise for deciding whether to search and supplies no evidence that it can nominate this replacement itself. DS26-0287 was already corrected by the unchanged earlier addition. Held DS26-0072 entered the original final matching fits and retained its incumbent. The alternative branch uses only the original frozen native detections and causal catalogue. The roof chart pairs genuine archived endpoints and labels the substitution as archive replay.

All 135 positions published in each arm, including 133 within 5 km, under both the cavity cutoff and the full preflight replay. The all-roof replay median/P95 was 0.982/2.941 km at `c=0` and 0.988/2.819 km with fitted `c`. The selected-final conditional RMS was also exactly preserved under replay, with medians 109.78 and 98.15 Hz. The archived cavity’s fit RMS was 71.17 and 71.05 Hz on its own retained observations, so these RF columns compare different selected support. [Scores by stage and arm](summary.json).

## Work avoided

| Original work opportunity | Total | Bypassed |
| --- | ---: | ---: |
| Whole reassociation calls | 135 | 16 |
| Ranked orbit families | 2,956 | 333 |
| Arm-specific leave-one-out evaluations | 5,912 | 666 |
| Nominated families | 231 | 29 |
| Proposals admitted to final fit | 2 | 0 |
| Final baseline / candidate arm-start fits | 8 / 8 | 0 / 0 |
| Repairs selected | 1 | 0 |

The 16 bypasses were all in the held split. The guard missed zero of its one held admissions and zero of the two overall admissions. Held sensitivity to a selected repair is unmeasured because that split had no selected repair. The replay preserved the two known diagnostic improvements in both arms. Median guard CPU on the archived, captured predecision feature port was 1.19 ms. The bypasses cover 706.44 s of 6,249.12 s of original ranking, admission, and final-stage wall time. This upper bound sums 137.17 s of ranking, 567.93 s of admission, and 1.35 s of final fallback time. It excludes residual addition and upstream analysis and is an archived work estimate, since the saved stage intervals ran on their original schedules.

## Fresh stored-GLRT replay

The fresh receiver ran both branches from complete capture-era native data through aligned compact v5. On DS26-0066 the guard took 1.38 ms, retained the original aligned candidate sequence including reassociation 62025→68047, and reproduced both previously sealed aligned coordinates and conditional RMS exactly. On DS29-0082 the guard took 0.62 ms, bypassed both archived nominated families and reproduced both positions and RF RMS exactly. Ranking plus admission plus final fallback on DS29-0082 took 0.0105 s in the new worker. The historical aligned run took 21.46 s across the same stages under its own schedule. The fresh checks authenticate the fixed request, catalogue and source and measure actual branch execution. Full-run speed ratios would require contemporary paired timing. [Fresh both-arm charts](live/charts/index.html), [fresh two-branch receipt](live/comparison.json), [fresh evidence seal](live/evidence-lock.json).

Both numerical workers completed their results. The initial outer launcher used the wrong field path for conditional RMS when assembling the comparison. The reported comparisons use the original authenticated worker files and read the metric from the checked v5 result schema. The replays did not need another numerical run. [Initial launcher bytes](live/initial-launcher.txt).

## Reproduction

Capture the authenticated original ZIP and execution receipts to local scratch, replay the rule, and build both standard distributions.

```sh
work=$(mktemp -d /tmp/leo-late-preflight.XXXXXX)
OPENBLAS_NUM_THREADS=1 taskset -c 15 python -m tools.pipeline_eval.qualification.late_preflight_trial --output "$work"
python -m tools.pipeline_eval.qualification.late_preflight_results --input "$work"
python -m tools.pipeline_eval figures --panel screening --variant late-preflight-roof135 --arm both --out /tmp/leo-late-preflight-charts
```

```sh
live=$(mktemp -d /tmp/leo-late-preflight-live.XXXXXX)
OPENBLAS_NUM_THREADS=1 taskset -c 11 python -m tools.pipeline_eval.qualification.late_preflight_live DS26-0066 --output "$live"
OPENBLAS_NUM_THREADS=1 taskset -c 19 python -m tools.pipeline_eval.qualification.late_preflight_live DS29-0082 --output "$live"
python -m tools.pipeline_eval.qualification.late_preflight_live_results --input "$live"
```

Render the fresh chart from the sealed worker results and aligned controls.

```sh
python -m tools.pipeline_eval.qualification.late_preflight_live_figures
python -m tools.pipeline_eval figures --panel screening --variant late-preflight-live --arm both --out /tmp/leo-late-preflight-live-charts
```
