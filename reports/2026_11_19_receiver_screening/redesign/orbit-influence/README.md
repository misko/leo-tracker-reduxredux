# Whole-orbit influence on archived native roof offers

The local orbit-influence gate rejected **6 of 7 false fixes** on the 104 prior roof offers while retaining **19 of 35 valid fixes**. The independent exterior gate also rejected six false fixes and retained **11 of 35 valid fixes**. The two gates retained different false offers. Whole-orbit influence retained 18 original-tile fixes and only one near-edge valid fix. Both calibration arms made identical decisions. The local diagnostic added median **65.8 ms** of wall time per evaluated archival offer. [Archival scores](diagnostic-stress/summary.json) · [Fitted-calibration figure](charts/fitted_c/native_smooth_orbit_influence-diagnostic-stress.png)

## Measured decisions

| Earlier roof offers | Native smooth | Whole-orbit influence | Independent held exterior |
|---|---:|---:|---:|
| Original containing | 23/26 | 18/26 | 7/26 |
| True site 1–2 km inside | 12/26 | 1/26 | 4/26 |
| True site 1–2 km outside | 3/26 | 0/26 | 1/26 |
| True site 6 km outside | 4/26 | 1/26 | 0/26 |

The local gate retained the 6 km omission on DS29-0316 at **11.20/11.19 km** error in `c = 0` and fitted `c`. Its zero-calibration centroid was 5.16 km inside the supplied square. The ellipse's nearest-edge margin was 0.71 km and the largest deletion shift was 1.62 km. The exterior gate retained the near omission on DS26-0102 at **4.55/4.68 km** error. Whole-orbit influence denied that offer. The two coordinates were retained exactly wherever their respective gates published. The covariance and phase assignments are local to the chosen solution, so a coherent incorrect fit can survive a whole-orbit perturbation. [Per-offer geographic, RF and geometry metrics](diagnostic-stress/scores.csv)

Published error on the 18 retained original offers was 1.425 / 2.510 / 2.544 km at median / P95 / maximum with `c = 0` and 1.159 / 2.570 / 2.588 km with fitted `c`. The one retained near-inside offer had errors of 4.554 and 4.628 km. The gate filters the original endpoints and leaves their conditional RF RMS and held metrics unchanged. Each arm's separate score is recorded for all forced fits. [Both calibration-arm distributions](diagnostic-stress/summary.json)

| Six reserve recordings | Native smooth | Whole-orbit influence | Independent held exterior |
|---|---:|---:|---:|
| Original containing | 5/6 | 4/6 | 0 published, 5 unmeasured |
| True site 1.5 km inside | 3/6 | 0/6 | 0/6 |
| True site 1.5 km outside | 0/6 | 0/6 | 0/6 |
| True site 6 km outside | 1/6 | 0/6 | 0/6 |

The local rule rejected the lone reserve false fix from DS26-0154 and all three near-edge valid publications. The resulting four valid original fixes had median errors of 1.873 and 1.601 km. The earlier exterior campaign measured four of nine tentative reserve publications and withheld every measured one. Five valid original-tile exterior checks were outside its replay budget. [Reserve per-offer results](reserve/scores.csv) · [Reserve position figure](charts/fitted_c/native_smooth_orbit_influence-reserve.png)

## Measured rule

The receiver used the frozen smooth oscillator on complete stored native GLRT factors. A fresh native replay rebuilt the Graph on every tentative publication and bound it to the earlier record's exact catalogue, request, assignments, clock-fit diagnostics and both calibration arm results. Initial smooth withholdings were inherited. The earlier independent held exterior result is carried as a third position series, including its unmeasured reserve rows. [Protocol](PROTOCOL.md) · [Frozen replay plan](plan.json)

At the smooth solution the adapter captures the existing final-state design and priors from the original bounded-fit entry point. Observations assigned to the same satellite are one block across tracks and radio lanes. Each deletion removes that block and resolves the local fit with the remaining data and all shared priors. The original nuisance bounds remain, and the two location coordinates are free in the deletion solve. The geographic shift is measured against the corresponding full local solution and applied at the original final fit. The prior and noise terms match the existing smooth design. This calculation uses the repository's same delete-group scatter helper and the same scatter formula used by the earlier exterior evidence, with a different source of displacement vectors. [Independent exterior method](../../recovery/exterior-evidence/README.md)

The publication rule requires the original point and every deletion point to be strictly inside the offered tangent square. It also requires the nominal 95% two-dimensional ellipse, formed from the sum of profile covariance and orbit-deletion scatter, to fit entirely inside the square. Both calibration arms must pass. The ellipse conditions on the assigned orbit identities, aliases, local Jacobian and residual scale. The external comparator uses independently held Doppler, a separately prepared chronological Graph and exterior square alternatives.

Two hash-selected opaque IDs underwent independent fixed-identity nonlinear deletion audits, both on original containing offers. The audits repeated the frozen clock refinement on the full rows and on each deleted orbit group from the same original starting fit, with geographic bounds released. Each audit shared the same profile covariance and substituted the nonlinear deletion shifts. DS26-0046 and DS29-0127 had 34 and 21 orbit groups per arm. The median approximate-to-nonlinear displacement error was 0.10–0.12 m across the four case-arm combinations. The largest shift error was 4.9 m and the largest ellipse projection half-width difference was 5.12 m. All four audit decisions agreed. Nonlinear refitting took 2.13–5.90 s per arm. [Sealed comparison](diagnostic-stress/summary.json)

## Runtime and provenance

All **51 fresh tentative replays** completed on one single-threaded worker pinned to CPU18 at nice +12 in **331.10 s**. No fresh runs failed or timed out. All 51 reconstructed Graphs, initial decisions and both fitted arm payloads matched their sealed smooth results. For the 42 archival offers invoking the local diagnostic, incremental CPU at median / P95 / maximum was **65.6 / 159.4 / 204.2 ms** and incremental wall was **65.8 / 174.8 / 204.2 ms**. The nine reserve jobs had median incremental wall of 55.0 ms. This timing excludes the two nonlinear audits. The routine full archived-factor replay wall median / P95 was 6.38 / 7.44 s, with peak RSS 154,208 KiB and peak virtual address space 394,716 KiB inside the 512 MiB cap. The independent exterior comparator used a separate earlier run, with median gate-only wall of 52.15 s and peak RSS of 699,912 KiB. [Archival prediction lock](diagnostic-stress/prediction-lock.json) · [Reserve prediction lock](reserve/prediction-lock.json)

## Reproduction

Use the verified native-lean deployed source bundle and a fresh scratch path. The original roof, boundary and exterior artifacts provide the authenticated input and reference lineage. The qualification uses the archived native files and causal catalogues. [Native source inventory](../../inference/native-lean/deployment.json)

```sh
influence_work=$(mktemp -d /tmp/leo-orbit-influence.XXXXXX)
timeout --kill-after=2s 720s nice -n 12 taskset -c 18 .venv/bin/python \
  -m tools.pipeline_eval.qualification.orbit_influence_trial --cpus 18 \
  --work "$influence_work/run" --bundle /path/to/deployed-source \
  --output "$influence_work/report"
.venv/bin/python -m tools.pipeline_eval.qualification.orbit_influence_results \
  --output "$influence_work/report"
```
