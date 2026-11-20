# Frozen exterior held evidence on real roof offers

The original exterior rule rejected **6 of 7** false smooth fixes across 52 omitted offers and **24 of 35** valid smooth fixes across 52 containing offers. The survivors were **1/52** false publications and **11/52** valid publications in each calibration arm. All 42 required exterior jobs on the archival cohort completed in 561.86 s. The gate-only median and P95 wall times were 52.15 and 65.30 s per job. [Archival scores](diagnostic-stress/summary.json)

## Earlier roof offers

The counts below use the entire scheduled condition group. The two arms had the same publication decisions. The error columns report the surviving fixes and give median / P95 / maximum geodesic error in kilometers. [Per-offer positions, held metrics and time](diagnostic-stress/scores.csv)

| Offered square | Smooth fixes | Smooth with exterior confirmation | `c = 0` surviving error | Fitted `c` surviving error |
|---|---:|---:|---:|---:|
| Original | 23/26 | 7/26 | 1.408 / 2.328 / 2.504 | 1.180 / 2.293 / 2.588 |
| True site 1–2 km inside | 12/26 | 4/26 | 1.049 / 4.087 / 4.554 | 0.693 / 4.044 / 4.628 |
| True site 1–2 km outside | 3/26 | 1/26 | 4.548 / 4.548 / 4.548 | 4.678 / 4.678 / 4.678 |
| True site 6 km outside | 4/26 | 0/26 | — | — |

The seven original false fixes came from five recordings. The remaining false offer was DS26-0102 with truth 1.889 km outside the supplied square. The frozen gate assigned it a conditional tile-mass lower bound of 0.9914 and a worst-delete-one-orbit held log-likelihood advantage of 0.0235. Its held RMS was 9.94 kHz for the interior and 9.95 kHz for the exterior. These are the exterior rule's held residual metrics. The gate retained the smooth position at 4.55 km error with `c = 0` and 4.68 km with fitted `c`. [Archival figure specification](diagnostic-stress/figures.json)

The other 30 tentative smooth fixes were denied as regionally ambiguous or supported by an exterior fit. The gate-only CPU time at median / P95 / maximum was 48.83 / 59.97 / 61.03 s, while wall time was 52.15 / 65.30 / 69.30 s. Maximum gate RSS was 699,912 KiB. This timing and memory cover the separate exterior worker after the smooth candidate. The original smooth worker's 512 MiB address-space limit applies to its own separate path. No exterior jobs failed, timed out or remained unmeasured in this archival cohort. [Archival resource distributions](diagnostic-stress/summary.json)

## Prospective reserve

All 24 fresh smooth controls completed on the six disjoint reserved DS26 captures. Smooth published on eight of 12 valid offers and one of 12 omissions. Four of those nine tentative publications received an exterior evaluation before the batch stopped at 654.34 s. The exterior gate denied the sole false publication and the three near-inside publications. The five original-offer publications remain unmeasured by the gate. Both calibration arms had the same decisions. [Reserve scores and missing outcomes](reserve/summary.json) · [Per-offer reserve CSV](reserve/scores.csv)

| Offered square | Smooth fixes | Exterior denials | Unmeasured tentative fixes |
|---|---:|---:|---:|
| Original | 5/6 | 0 | 5 |
| True site 1.5 km inside | 3/6 | 3 | 0 |
| True site 1.5 km outside | 0/6 | 0 | 0 |
| True site 6 km outside | 1/6 | 1 | 0 |

The denied false proposal was DS26-0154 with a zero-calibration error of 13.87 km and a conditional mass lower bound of 0.030. The four measured exterior jobs took 46.27–51.88 s each, with zero failures and timeouts. The independent positive-retention measurement is limited to the three near-edge positives. [Reserve figure specification](reserve/figures.json) · [Both arms, position charts](charts/)

## Receiver boundary

The reported candidate applies one geographic verdict to a tentative two-arm native smooth-oscillator publication. The original smooth receiver and the gated receiver use identical native factors, supplied offer, latest causal catalogue, anonymous smooth Graph and fitted coordinates. The exterior rule separately rebuilds its original chronological development Graph from those same native factors and uses the authenticated causal TLE history. The history's last catalogue matches the smooth receiver's catalogue. Its independent held samples come from the last three seconds of each 12-second block, excluded before that rule forms development tracks. The exterior worker receives the offer and native/history assets without receiving smooth endpoints, truth or query conditions. [Frozen protocol](PROTOCOL.md) · [Exact input and source plan](plan.json)

The exterior stage uses the existing wide initialization, development-selected orbit identities, four exterior half-boxes, development-calibrated curvature, and delete-one-orbit scatter. Publication requires the frozen 95% tile-mass lower bound conditional on the screen and its selected identities, and the original held-likelihood advantages. The qualification adapter stops before the historical compact-v5 cavity and retains the frozen geographic result. It applies that verdict to both smooth arms. Frequency metrics in the position score are smooth conditional RMS, while the exterior stage reports its own interior and exterior held RMS and likelihood separately. The held-arc hashes match across all offers from each recording. The original geographic projection differs from the smooth tangent frame by at most 27.4 m on the tested true margins, with identical in/out membership on all archival offers. [Frozen gate qualification](../../factors/region-support/development-noise/README.md)

All 104 archival offers come from 26 distinct RF captures at one roof site. They are a diagnostic cohort since their earlier boundary errors are known. Only tentative publications require the expensive exterior evaluation, and the plain smooth receiver's initial withholdings remain. New prospective work was reserved by opaque hash on six entirely different DS26 captures with separately generated offers. The reserve is evaluated only within the shared cap. [Archival prediction seal](diagnostic-stress/prediction-lock.json) · [Reserve prediction seal](reserve/prediction-lock.json)

## Reproduction

Use a verified native-lean deployed source bundle, the frozen v5 source and compiled kernel inputs, and local output paths. The study rebuilds the exterior projector from its pinned source. The runner applies a 90 s deadline to each exterior job and 60 s to each fresh smooth control. The outer cap is shared with the reserve. [Native deployment inventory](../../inference/native-lean/deployment.json)

```sh
exterior_work=$(mktemp -d /tmp/leo-exterior-evidence.XXXXXX)
timeout --kill-after=2s 720s taskset -c 8,9,16,18 .venv/bin/python \
  -m tools.pipeline_eval.qualification.exterior_evidence_trial \
  --work "$exterior_work/run" --bundle /path/to/deployed-source \
  --output "$exterior_work/report"
.venv/bin/python -m tools.pipeline_eval.qualification.exterior_evidence_results \
  --work "$exterior_work/run" --output "$exterior_work/report"
```
