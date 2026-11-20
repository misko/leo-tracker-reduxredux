# Prospective aligned Armijo finish confirmation

All 15 prospective recordings published in both calibration arms, as did
the four separately selected stress cases. Prospective median/P95 position
error was 0.881/2.038 km with `c = 0` and 0.912/2.022 km with fitted `c`.
Fourteen of 15 errors in each arm were within 10% of original no-repair v5
or better. Six prospective cases adopted new residual families. The
short-vector correction did not trigger on these 19 recordings.
[Per-recording scores](scores.csv)

The frozen aligned finish was applied to eight DS26 inputs selected by a
fixed opaque-ID hash and the seven DS29 inputs outside the earlier aligned
retrospective run. Four known cavity loss or displacement cases form a
separate stress group. The worker starts with archived native GLRT factors,
matched causal TLEs and the original 25 km tile. Both calibration arms use
the same initial branches, observations and configuration. [Protocol](PROTOCOL.md) · [Frozen roster](roster.json)

The exact matched controls are the sealed full-panel secant and stock
compact cavity results and the four original v5 publication options. The
candidate runs through residual addition and final reassociation beyond the
archived cavity outputs. The controls use the same request binding and retain
their recorded computation boundaries. The original v5 controls also retain
their own reported publication RMS. [Predictions](prediction-lock.json) · [Original v5 request and execution bindings](original-v5-inputs.json)

The code records conditional Doppler RMS in hertz and the final numerical
objective from the `frequency_score` field separately. The finish emitter
uses negative twice ELBO when supplied by the selected state and the
objective field otherwise. The archived cavity position records supply
conditional RMS. Geographic scoring uses the independent location reference
after the prediction seal.

## Prospective position and frequency results

Every method published all 15 positions and had 14 within 2 km in each arm.
The table gives geodesic median, P95 and maximum in kilometers on the exact
same recordings. [Distributions and paired counts](summary.json)

| Method | `c0` median / P95 / max | Fitted `c` median / P95 / max | Aligned error at most +10%, `c0` / fitted `c` |
|---|---:|---:|---:|
| Aligned Armijo full finish | 0.881 / 2.038 / 2.196 | 0.912 / 2.022 / 2.163 | — |
| Archived secant cavity | 0.886 / 2.055 / 2.251 | 0.918 / 2.040 / 2.221 | 14 / 14 |
| Archived stock compact cavity | 0.885 / 2.049 / 2.246 | 0.917 / 2.035 / 2.215 | 14 / 14 |
| Original no-repair v5 | 0.885 / 2.034 / 2.195 | 0.917 / 2.020 / 2.164 | 14 / 14 |
| Original selective-gap | 0.823 / 2.034 / 2.195 | 0.758 / 2.020 / 2.164 | 13 / 13 |
| Original omitted-track-one | 0.881 / 2.034 / 2.195 | 0.912 / 2.020 / 2.164 | 12 / 12 |
| Original omitted-tracks | 0.881 / 2.034 / 2.195 | 0.912 / 2.020 / 2.164 | 12 / 12 |

DS26 aligned medians were 0.905 and 0.860 km, with 2.117 and 2.093 km P95.
DS29 aligned medians were 0.881 and 0.912 km, with 1.222 and 1.329 km P95.
The largest aligned displacement from original no-repair was 188 and 180 m.
No prospective error increased by over 100 m against no-repair or either
cavity control. One per arm exceeded that increase against selective-gap.

Median conditional Doppler RMS on the prospective cohort was 68.186 and
68.164 Hz for aligned finish, 68.898 Hz in both arms for secant cavity and
68.898 Hz in both arms for stock compact cavity. The final aligned objective
medians were 27,832.676 and 27,829.882. The cavity controls omit that score.
Original no-repair reported median publication RMS of 108.747 and 94.435 Hz
and objective medians of 27,455.973 and 27,470.555 under its own publication
contract. Support and output boundaries differ between the full finish and
cavity, so these measurements describe each recorded endpoint separately.
[Case-level frequency and objective fields](scores.csv)

## Separate stress results

On the four stress cases the aligned results stayed within 0.405 m of the
archived secant cavity coordinates. The error increases on DS26-0152 and
DS26-0283 persisted against compact stock and the original v5 options.
The displacements on DS26-0092 and DS26-0072 again reduced geodesic error
against those controls. Each table entry gives `c0` and fitted `c` error in
kilometers. [Stress prediction lock](stress-lock.json)

| Recording | Aligned finish | Compact stock and no-repair v5 |
|---|---:|---:|
| DS26-0152 | 0.7504 / 0.9396 | 0.6742 / 0.8432 |
| DS26-0283 | 0.0563 / 0.0634 | 0.0458 / 0.0521 |
| DS26-0092 | 0.9767 / 1.1083 | 2.7781 / 2.5001 |
| DS26-0072 | 3.7105 / 3.7024 | 4.3546 / 4.3291 |

## Decisions and resource use

Six prospective recordings qualified a residual addition. DS26-0076,
DS26-0114, DS26-0058, DS29-0174, DS29-0316 and DS29-0519 added 34, 50, 70,
26, 43 and 28 points respectively in each arm. No stress case qualified an
addition. DS26-0072 was the only recording with an admitted reassociation.
Its remap used the equal-length phase path and the reassociation remained
unselected. The shortened phase-vector guard has its prior positive case in
the separate retrospective DS26-0066 run.
[Worker metrics](positions.jsonl.gz) · [Prior retrospective evidence](../../armijo-finish/aligned/README.md)

The 19 candidate attempts took 768.80 s elapsed on eight pinned CPUs.
Prospective worker wall times ranged from 146.06 to 455.56 s, with a
274.16 s median. Median worker CPU was 238.23 s and maximum was 370.84 s.
Numerical peak RSS had a median of 1,593,000 KiB and a maximum of
1,953,752 KiB. Stress worker median wall and CPU were 250.13 and 223.02 s,
with a numerical peak RSS maximum of 1,718,128 KiB. Archived position
controls retain their historical times and no control was replayed here.
[Runtime distributions](summary.json) · [Supervisor and prediction seal](prediction-lock.json)

## Reproduction

The supervisor ran as a detached user service with a 20-minute cgroup
limit. Each candidate worker uses one numerical thread on cores 12–19 and
a deadline no longer than 480 seconds. `scores.csv` records wall and CPU
for the candidate wrapper and its children. Numerical peak RSS comes from
the inference worker, and child peak RSS covers the largest waited child.

```sh
aligned_work=$(mktemp -d /srv/bulk/leo-dev/leo-aligned-confirm.XXXXXX)
taskset -c 12-19 env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python \
  -m tools.pipeline_eval.qualification.aligned_confirmation run \
  --work "$aligned_work" --output "$aligned_work/report"
.venv/bin/python -m tools.pipeline_eval.qualification.aligned_confirmation_results seal \
  --work "$aligned_work" --output "$aligned_work/report"
.venv/bin/python -m tools.pipeline_eval.qualification.aligned_confirmation_results score \
  --output "$aligned_work/report"
```

The screening figure loader reads separate sealed confirmation and stress
charts from the local declarative specification. [Figures](figures.json)
