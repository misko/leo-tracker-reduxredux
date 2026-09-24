# DS1 iteration 2: ranked path toward sub-kilometre positioning

## Decision

The first next experiment should be a **joint geographic, global-time, and
causal per-NORAD phase-rate fit**, with a DS1-native TRAIN-only association
policy.  It must be run first as a fixed-ID control and then with association
reselection.  The existing one-hour result does not reject this hypothesis:
it applies the rate only after an RF-selected geographic finalist has already
been chosen, on a 12.5 km final grid.  It therefore can lower RF loss without
having any route to move the selected geographic cell.

This is the only candidate with a large, matched historical effect.  In the
formal fixed-ID archive, removing per-NORAD RF orbit refinement changed error
from 328.4 m to 3.137 km.  DS1's global time correction already removes a
common component, improving the full-block median from 5.534 to 3.364 km, but
it has no satellite-specific orbital term.  This makes a rate-plus-time
ablation the most informative way to test whether the remaining kilometre
bias is source-specific orbit mismatch rather than geographic grid resolution
or a single receiver clock shift.

No iteration below may use a reference coordinate, reference error, validation
rows, TEST rows, old selected NORAD lists, old candidate unions, or historical
winning seeds in its optimizer.  All can be developed on DS1 TRAIN.  For model
selection within TRAIN, retain DS1's randomized observation masks for inner
prediction and, when choosing among families or hyperparameters, use a frozen
whole-scan/group split rather than geographic error.  The post-seal evaluator
may attach the reference coordinate only after every selected inference is
sealed.

## What the earlier sub-kilometre results actually changed

| Aspect | Strongest historical result | Current DS1 / one-hour treatment | Consequence |
|---|---|---|---|
| Orbit physics | Causal phase mean plus one bounded, regularized phase-rate per fixed NORAD; rate affected the location fit | DS1 baseline has only a global tau. The bounded DS1 rate and one-hour rate are applied at selected finalists | The large historical mechanism has not yet been tested as a location-selecting DS1 model. |
| Receiver time | No fitted receiver clock in the 328 m formal result | One tau shared by every track, satellite, receiver and scan | Tau is useful, but cannot model different TLE-age errors by satellite. |
| Identity | 446 fixed identities inherited from prior full-archive/site-conditioned analysis | Dynamic full-catalogue TRAIN candidate selection at each point/tau | Historical accuracy is conditional on identity. DS1 is more honest but its association/rate interaction is still unmeasured. |
| Noise model | Learned scale; formal version also AR(1) whitening and Student-t innovations | Occupied-second weighted, 800 Hz-capped squared RMS | Likelihood differences are secondary until rate physics is tested under a common identity rule. |
| Data and search | 622 episodes/21,702 observations from 211 recordings; continuous local fit | DS1 has 1/6/16/all views of five frozen groups; one-hour screen uses only first 1/6 scans in two TRAIN groups | The cohorts and conditioning differ; an old point error is not an expected DS1 error. |
| One-hour execution | Not applicable | All observations, no inner holdout, two groups × 1/6 scans × two priors; +/-2 s at 0.5 s; final grid 12.5 km | It is a fast mechanism screen, not a sub-km resolution or generalization result. |

The one-hour rate evidence is still useful.  Its rate-only and tau+rate arms
lowered their own RF objective, while retaining the baseline and global-time
cells exactly.  For example, one singleton rate fit had 22 NORAD rates and two
bound hits.  The bounded exact DS1 implementation separately passed its
0.2 Hz direct-SGP4 gate by four orders of magnitude, but evaluated only the
ordinary TRAIN-ranked top one/four pairs and likewise did not move the point.
These results support the numerical feasibility of the rate nuisance; they do
not test its geographic effect.

Several apparent earlier wins must not be revived as targets.  The 292 m
configured-site result is 1.579 km after the corrected antenna reference.  The
314 m sixteen-scan result used historically exposed candidate/seed discovery;
the training-only replay was 412 m and related day validation had a 4.321 km
median with no group below 1 km.  The 631 m independent per-track timing fit
reversed on another group and used timing freedom beyond the measured authority.
The 348 m dual-LNB beam proxy lost to shuffled controls.  These are negative
controls, not ingredients for the primary arm.

## Ranked iterations

| Rank | Iteration and TRAIN-only decision rule | Expected gain | Compute cost | Can run on TRAIN without truth in optimizer? |
|---:|---|---|---|---|
| 1 | **Joint causal rate + global tau, fixed-ID then reselected-ID.** At every geographic/tau candidate, fit a causal per-NORAD rate using the frozen 0.091766 s/h zero-centred prior and +/-0.25 s/h bound; choose location from TRAIN objective. Fixed IDs are selected once from that arm's TRAIN rows, then a matched dynamic-reselection arm is run. | High potential; the only matched historical ablation showed a 2.81 km reduction when rates were present. No DS1 magnitude is promised. | High. Exact-node rate fitting is about 20–25 s per ordinary pair; use a surrogate for search, exact replay for every retained geographic finalist. Parallelize by sealed arm, not by shared mutable state. | Yes. Use current DS1 causal catalogue/cache, TRAIN masks and no reference fields. |
| 2 | **Causal history mean + rate decomposition.** Add the pre-capture causal phase mean before the residual rate, then compare mean-only, rate-only, tau-only and mean+rate+tau on identical points/IDs. | Low-to-moderate but clean. The archived causal point prior improved 4.859 to 3.787 km before RF-updated rates. It may reduce rate bound hits and tau/rate confounding. | Medium; cheap relative to rate fitting once exact state nodes exist. | Yes, provided every catalogue transition and element precedes its capture. |
| 3 | **Fine local paired search of the winning rate model.** Start from both declared priors, retain all RF-selected basins, and refine to at least DS1's 0.15625 km spacing with exact finalist replay. This is paired with tau-only, not an error-driven rescue. | Diagnostic rather than a physics gain. It separates the one-hour 12.5 km quantization limit from genuine model bias. Existing full DS1 shared-tau fits at 0.15625 km show grid refinement alone is unlikely to create a general sub-km result. | Medium-high when attached to rank 1; low incremental cost after finalists are known. | Yes. Stopping, basin count, refinement levels and ties must be predeclared. |
| 4 | **Learned-scale Gaussian likelihood under the rank-1 identity/rate policy.** Hold associations, geography and rate prior fixed; compare current capped loss with a learned-scale independent Gaussian. Only then add AR(1)+Student-t as a second ablation. | Moderate/uncertain. In the formal archive, Gaussian learned-scale was 335.7 m, close to 328.4 m formal; this says scale may matter while correlation is not the first DS1 bet. | Medium for Gaussian; high for AR(1)+Student-t and exact rate replays. | Yes. Fit scale/hyperparameters on TRAIN or a frozen TRAIN inner split; do not select them by location error. |
| 5 | **Regularized scan residual time around global tau.** Compare tau-only with `tau_scan = tau_global + delta_scan`, with a zero-mean gauge and predeclared 0.2/1/5 s scales. Run both fixed-ID and reselected-ID versions after rank 1. | Low-to-moderate. It reached 0.886 km on one 79-scan TRAIN block but selected 5 s by TRAIN loss and had a 2.471 km validation median. The one-hour screen chose the same cells as global tau. | Low-medium; a grid/profiled timing layer is much cheaper than exact rate fitting. | Yes. Select scale using both complete TRAIN groups and TRAIN prediction only. |
| 6 | **TRAIN-native soft association with a null option, after hard-rate control.** Keep a short, full-catalogue candidate set per track, fixed prior mass, explicit null/outlier cost and candidate entropy; compare hard versus soft under the same rate/tau physics. | Uncertain and not expected to be a primary gain. Earlier mixture fitting changed 2.007 to 2.040 km; the one-hour soft+tau median matched tau but its worst arm was 17.553 km. Its value is avoiding brittle wrong-ID fits. | High, especially if rates are integrated rather than staged. Start on fixed geographic points and a limited candidate budget. | Yes. Candidate universe, null mass, component scale and truncation rule must be frozen from TRAIN only. |
| 7 | **Pass/episode balance and influence audit of rank-1 winners.** Compare occupied-second, episode and recording–NORAD/pass-balanced weights; report predeclared NORAD and pass deletion folds. | Small expected movement, high value for credibility. Prior pass balance improved a conditional error by hundreds of metres and reduced maximum deletion shifts, but is not evidence of DS1 transfer. | Low-medium; reuse sealed rank-1 outputs/state Jacobians where valid. | Yes. Weights and folds are fixed before reference evaluation. |

Ranks 1–3 are one nested experiment, not three chances to choose the location
nearest the reference.  Rank 2 is a causal-physics ablation within rank 1; rank
3 is the predeclared resolution stage for any retained RF-selected basin.  Do
not run ranks 4–7 in parallel and choose their winner from the known coordinate.
First freeze a small family after complete TRAIN results, then replay that
family on both validation groups with the same source/input hashes and full
failure accounting.

## Required safeguards and measurements for rank 1

The causal rate must advance SGP4 orbital propagation while Earth rotation
remains at receive time plus global tau.  The rejected cache-indexed prototype
advanced both and had 413 Hz RMS / 1,019 Hz maximum direct discrepancy.  Each
completed rate arm needs exact SGP4 replay at the final rates and a maximum
Doppler discrepancy no greater than 0.2 Hz.  Retain nonconvergences, failed
exact gates, optimizer iteration counts, candidate changes, rate count, rate
bound hits, phase range, and per-NORAD recurrence; do not drop difficult arms.

The rate prior is a model guardrail, not proof that each fitted rate is an
orbit error.  A per-NORAD phase correction can absorb clock error, source
frequency structure, or an incorrect identity.  This is why the fixed-ID
control and the reselected-ID arm must share exact geographic traces, masks,
weights, candidate visibility and CFO profiling.  The fixed-ID control may
freeze only candidates chosen from its own TRAIN rows at a sealed anchor or
first pass.  It must never import the old 446 IDs, the historical site-selected
population, the Sausalito coordinate, or a validation-selected identity.

Use two evaluation layers without conflating them:

1. Randomized held observations within TRAIN test within-track frequency
   prediction and must never select location, tau, rates, identity, geographic
   expansion or model family.
2. Whole frozen validation groups test transfer of the frozen configuration.
   Their coordinate errors and held metrics are evaluation outputs, not tuning
   signals.  The exposed TEST group remains regression evidence, not a new
   untouched final test.

## Explicit deferrals

Independent +/-5 s per-track timing is diagnostic only: DS1 found 3–10% exact
boundary choices, and the historical fit had roughly 96% noninteger selected
times.  A fractional common clock within measured brackets is reasonable as a
resolution audit, but it should not be made the primary estimator.

Pointing cones and dual-receiver geometry should remain association-consistency
checks.  The current 5-degree orientation grid and tens-of-degrees required
cones cannot resolve a 300 m displacement (about 0.017 degrees at 1,000 km);
the narrow 10-degree cone retained only about 1% occupied-second support.
Adding it to the position objective would be a costly, weakly calibrated
constraint.  Receiver drift and beam-response proxies are also deferred because
they reduced residuals without reliable location transfer or lost to controls.

## Evidence consulted

- `../2026_09_24_ds1/REPORT.md` — paired DS1 baseline/global-tau result and
  0.15625 km local refinement.
- `../2026_09_24_ds1_train_full/REPORT.md` — completed one-hour 64-task,
  full-observation 12.5 km screen.
- `../2026_09_24_ds1_orbit_arm/REPORT.md` — exact, bounded DS1 rate feasibility
  and its selected-finalist limitation.
- `../2026_09_24_ds1_subkm_ablations/REPORT.md` and
  `../2026_09_24_subkm_reconciliation/REPORT.md` — matched reconciliation of
  historical claims and DS1 transfer matrix.
- `../2026_09_21_causal_orbit_error_model.md` and
  `../2026_09_21_position_ablation_report.md` — causal rate prior, fixed-ID
  limits and formal matched ablations.
- `../2026_09_24_ds1_timing_ablations/REPORT.md` — fixed-ID timing transfer
  limits and boundary diagnostics.
- `../2026_09_22_joint_circular_position/README.md`,
  `../2026_09_23_soft_candidate_position/README.md`, and
  `../2026_09_23_train_pointing_cone/REPORT.md` — soft-association and
  geometry limitations.
