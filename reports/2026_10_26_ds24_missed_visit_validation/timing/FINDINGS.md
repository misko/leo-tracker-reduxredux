# Primary quadratic timing helps; sparse search remains complementary

On the fixed development panel of 288 paired windows and 576 receiver owners,
the primary quadratic/fallback point yields **141 admissions**, versus **45
consistent linear** and **33 legacy-adapter linear**. Admissions require both
the pilot margin and compatibility with the earlier CFO width. Quadratic adds
9 owners absent from original detections, including 6 in CH5–8. These are
provisional RF candidates, not accepted tracks or evidence of better position
accuracy. No held raw outcomes or positions enter this development report.

## Matched full-window comparison

Each method uses the same earlier primary branch, CFO forecast and full 20 ms
target. There is no target timing or mode search. Quadratic/fallback alone is
the proposed operational policy; a passing control never rescues it. Consistent
linear epochs go directly to the scorer. Legacy reproduces R01's extra
rate × 0.010 s advance as a descriptive control. Midpoint-effective timing is a
nominal convention; actual pilot weighting can differ. R01/R02 change sample
exposure, mode policy and references as well as curvature.

| Native owners | Original full 20 ms | Linear admissions | Quadratic admissions | Legacy admissions | R01 search admissions |
|---|---:|---:|---:|---:|---:|
| All 576 | 165 | 45 | 141 | 33 | 182 |
| CH5–8, 384 | 69 | 21 | 60 | 12 | 86 |
| New original-absent, all | — | 4 | 9 | 3 | 30 |
| New original-absent, CH5–8 | — | 2 | 6 | 2 | 23 |

Quadratic/fallback has 99 paired gains and 3 losses versus consistent linear;
CH5–8 has 39 gains and no losses. Among 289 eligible quadratic cells, admissions
rise from 26 to 122. All 164 fallback cells retain their linear score exactly,
with 19 admissions in either arm. The 123 no-donor cells remain unavailable.
This is a useful point proposal on eligible histories, but most new R01 owners
used sparse histories or alternative modes. No union or hybrid is selected.

![Matched primary full-window arms](fullwindow_primary_timing.png)

The 141 quadratic admissions comprise 132 originally positive owners and 9 new
ones; they cannot simply replace the original 165. There are 145 **pilot
confirmations** from the margin alone, of which 4 fail earlier-CFO compatibility.
The candidate manifest preserves these decisions, native ownership and donor
conditioning. Coherence, curvature and causal all-catalogue association remain
separate requirements. No independent new likelihood point is admitted here.

## Frequency information and grid origin

The historical 512-bin GLRT64 profile retains 443.892045 Hz spacing and earlier
rate dechirping at each frame. It scores later complex samples without a donor
posterior penalty. Among 141 quadratic admissions, 125 select residual bin zero
and 16 select nonzero bins, reaching 5,326.70 Hz. All innovations are integer
multiples of the grid spacing relative to the earlier prediction. A zero bin
supports a pilot near the forecast; it is not calibrated fine CFO precision or
another independent donor observation. The forecast determines the grid origin.

The frozen controls deliberately use prediction errors of ±750 Hz, ±2,500 Hz
and ±half a frequency bin, both edges and signs. CFO evolves at ±2,000 Hz/s;
earlier and target midpoint counters differ by exactly 0.354 s. Carrier phase
and timing evolution use explicit midpoint references. Truth belongs only to
generation/evaluation. Identical method points isolate scorer sensitivity;
these controls do not establish natural quadratic forecast accuracy.

All 48 primary strong trials at ±0.5 sample timing error are admitted within
500 Hz; **0/48 are within 100 Hz**. In the 32 cases whose earlier CFO error
exceeds 500 Hz, carry is accurate in 0/32 and the later-bin estimate in 32/32.
Their CFO RMSE falls from 1,845.60 to 156.40 Hz. Later samples therefore supply
frequency information beyond accurate carry, while the tested grid origins
still prevent a fine-precision claim.

The separate 48 strong trials at ±3.5 sample timing mismatch also fall within
500 Hz. This is a stress result, not a general timing-repair claim. No admitted
strong error exceeds 1 kHz. Weak trials yield 69/96 admissions, including 67
within 500 Hz. One unadmitted gross error remains: trial 60, lower edge,
−3.5 sample mismatch, CFO error −26,411.58 Hz. No admitted weak error exceeds
1 kHz. All errors and availability remain in the compact trial table.

![Frequency innovation and grid origin](frequency_innovation_and_grid_origin.png)

Conditional Gaussian nulls yield zero pilot confirmations and admissions in
each 32-trial edge × identical/distinct point stratum: 128 independent targets.
Each exact one-sided 95% upper bound is 8.937%. The descriptive method union is
also zero and never becomes operational acceptance. All 32 wrong-sequence
controls yield zero pilot confirmations and admissions. These pass the frozen
exploratory screen, not deployment FAR, calibrated RF uncertainty, a panel-wide
guarantee or natural identity validation. R01's separate 80-target half-cell
diagnostic is context; no duplicate timing-bank experiment is run here.

## Ownership, runtime and verification

Every source is freshly exhausted through public FastSegmentSource and checked
against native index, IQ, acquisition and target authority. Old paired blind
parity is reused only at these exact 288 previously verified R01 windows under
the unchanged runtime. No repeated blind production acquisition occurs, and
receipts label the reuse. Modes and controls share each target owner.

All 288 windows and 576 unique owners complete without failure. Seven tests
cover public-score parity, direct references, control rejection, score reuse,
reader exhaustion and analytic carrier/counter conventions. Full checkpoints
retain every window. The initial fabricated-fixture wrapper error was fixed
before freezing and recorded. Scientific sources and numerical artifacts remain
unchanged; this revision only improves report and plot labels.

Raw shards sum 173.68 process-seconds: 57.39 for reading/verification, 102.16 for
new scoring and 14.14 for checks/serialization/checkpoints. Two workers take
roughly 1.5 minutes wall time. R01 summed 735.80 seconds, including 403.18 seconds
of repeated blind parity. That changes both parity and scoring workload and
is not a pure algorithm speed comparison. Signal/null/wrong controls take
23.53/12.49/4.93 seconds. All processes use BLAS1 and 580-second bounds. There is
no new RF, QNAP write, production change, git mutation or position execution.

Use the repository Python, exact historical source PYTHONPATH and BLAS thread
variables set to 1. Run `python -m unittest -v test_scorer`. Harness commands
are `study.py signal`, `null`, `wrong`, and `recorded --case CASE`, subject to
hash-bound root authorization. Outputs are exclusive; reproduce in a separate
copy. Source/tests, compact trials/cells, candidates, figures and seals form
the development publication. Full outcomes/checkpoints remain local and raw
IQ stays external. Coherent R01 application and held validation have separate
source seals and authorization.
