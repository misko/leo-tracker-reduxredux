# C081 matched views and common-calibration anchor cycle

The combined native-clock fit still trails the upper band. A matched
calibration-profile/release cycle improves full error modestly to12.785305 km,
but does not close that gap or reach sub-kilometre accuracy.

| Matched likelihood view | Selected error (km) | Objective | NLL | KKT |
|---|---:|---:|---:|---:|
| CH1–8 | 13.934381 | 26093.650843 | 25699.474515 | 0.000103683 |
| CH1–4 | 14.409464 | 15576.615667 | 15231.547647 | 0.000182011 |
| CH5–8 | 9.513268 | 10515.825042 | 10171.680101 | 0.000026875 |

All six fits, two starts per view, pass strict KKT checks. Every view selects
the same nearby source region. Selected radii3.275/4.259/4.098 km are interior
to their25 km disks, so geographic boundary expansion is not indicated.
Both original clock endpoints required zero initializer adjustment. Bank,
frame, priors and initializers are shared full-derived inputs; this remains
a conditional likelihood ablation rather than independent half discovery.
Six new fits used20 seconds/600 iterations each; runtime48.692 seconds.

Next, every training-derived view position initialized a full-likelihood
fixed-position fit with exactly the same full non-position state. Accepted
profiles received a free-position continuation in the unchanged original25 km
disk; original full incumbent remained eligible.

| Anchor | Profile result | Released objective | Released error (km) |
|---|---|---:|---:|
| Full | Accepted, J26093.650843 | 26093.650843 | 13.934381 |
| Low | Accepted, J26048.347462 | 26043.283318 | 12.785305 |
| High | Nonstationary, J27531.101924, KKT1684.523833 | Not run | Unavailable |

The low-origin release wins the training selector: NLL25638.756309,
KKT0.000052961, radius3.163428 km. The high profile is retained as a failed
attempt without retry or release; its raw objective is not selectable.
Five calls ran in68.467 seconds. All outcomes were sealed before reference
evaluation. No model, cohort baseline or histogram is promoted.

Six component tests across view/cycle drivers and evaluators, plus Ruff, pass.
View driver `fbe3fc9b7`, evaluator `42f096912`; cycle driver `2e99a7c30`,
evaluator `d0cc206c1`.
Bulk root `/srv/bulk/leo-research-ds21-ds22/2026_10_14`.
Views namespace `model-c-clock-views-081-v1`, terminal SHA256
`121985c4137f9e873b93cb94c28f2a0280e3e542061d8a96d424cd55ba1ff369`.
Cycle namespace `model-c-anchor-cycle-081-v1`, terminal SHA256
`2827a529f8cc22ba99cfb426911210890b5c9fd537ea36b4f107378e8c37770a`.
Cycle seal SHA256 `258b3f492197def3a84b2a8d758762514e5a0a1017940bbd3680479db2cf335e`.

Potential next distinct control: qualify complete existing B calibration,
clock and satellite timing states under C's native likelihood using the
source-modal receiver integer lifts. This tests a different nuisance basin,
not another geometry-only anchor or unsupported radius expansion. Any trial
must preserve original disks and compare training scores only within C.
