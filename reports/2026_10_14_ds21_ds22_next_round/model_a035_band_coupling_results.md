# A035: coupled half-view calibration states, without a new fit

The bounded audit completes in **13.127 seconds**, with **34 wrapper objective evaluations and zero optimizer calls**. It uses the current accepted shared and band-contrast models on the same fixed 55-satellite bank, frozen frequency shifts and original 25 km disk. No configured reference or held measurements enter the audit.

Every earlier half endpoint is replayed before choosing the lowest-J eligible own-view state. The current matched states remain selected. Two historical states remain eligible but have higher J. A previous HIGH state has lower half J11540.751 than current J11701.259, but fails strict KKT at 0.004184 and remains unavailable. A fresh historical LOW endpoint accepted by the hard model fails the new smooth model at KKT0.001907: the objective changes by only −1.5e−7, but the horizon derivative changes by 0.001636. This is an explicit model requalification failure, not exclusion because its initializer is older. No tolerance is relaxed.

| Current full state | Full J | Full NLL | LOW likelihood geography gradient | HIGH likelihood geography gradient |
|---|---:|---:|---|---|
| Shared q | 28882.674 | 28571.605 | [−8.391, +300.762] | [+8.391, −300.762] |
| Band contrast q | 28647.017 | 28323.944 | [−15.246, +294.074] | [+15.245, −294.074] |

Each full optimum balances opposing band gradients. That cancellation is required by first-order stationarity and is not itself evidence of misspecification. Adding band contrast improves both bands' in-sample NLL but moves geography by only about 42 m; its earlier opposite-fold NLL is worse by 469.018. The previously reported configured distances remain 7.223/7.264 km. These facts do not establish an isolated clock, RF or timing defect.

The complete own-half states have worse full-model training objectives than the complete full state, even though their own band is better:

| Model | LOW complete state: full ΔJ | HIGH complete state: full ΔJ | LOW timing / clock RMS change | HIGH timing / clock RMS change |
|---|---:|---:|---|---|
| Shared q | +277.909 | +1469.421 | 0.955 s / 60.361 Hz | 3.419 s / 245.365 Hz |
| Band contrast q | +607.218 | +1959.320 | 1.118 s / 49.500 Hz | 3.035 s / 238.966 Hz |

RMS changes compare satellite absolute timings and common-clock coefficients against the full state in the same frame. They are descriptions of coupled fitted states, not independently measured instrumental drift. Candidate-mass distribution total variation changes by 0.022–0.049 in the respective half; raw posterior and supported-row summaries remain in the scientific receipt.

All prespecified single-block swaps worsen their own full-model objective:

| Swap at full likelihood | Shared ΔJ | Contrast ΔJ |
|---|---:|---:|
| LOW geography, full nongeography | +198.700 | +365.881 |
| Full geography, LOW complete nongeography | +397.682 | +853.856 |
| HIGH geography, full nongeography | +10541.441 | +10717.270 |
| Full geography, HIGH complete nongeography | +10467.917 | +10370.823 |

The much larger separate swap costs than the complete HIGH-state cost show strong geography/calibration/timing coupling. They do not prove that profiling cannot find another basin, nor that the current objective is globally correct. Full/LOW/HIGH likelihoods and prior-corrected physical/nuisance gradients partition exactly at every tested state. Timing, clock, shared-q and contrast-q priors are accounted separately; no scores rank different models against each other.

The next authorized control is a finite fixed-profile/release experiment: shared/contrast × own LOW/HIGH geography × full/half complete nongeography. Fit all eight fixed-geography profiles first; after their barrier, release every accepted complete profile, at most eight more fits. Retain each current full incumbent. This tests whether nuisance refitting can cross a coupled basin without any reference-selected position, changed bank, disk or tolerance. Both halves already have roughly 7 km configured distances, so it is not presented as a simple fusion fix or a subkilometer guarantee. No such fit is included in this audit.

Source: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-a035-band-coupling-audit-v1`, source commit `ca29f719e`, scientific seal `sha256:307acdcbcd7ef6ad280f5e49888a08686105259c19ae7c2a660d32f2b3f3c662`. Five component tests and Ruff pass. The external whole-process cap is 135-second TERM / 140-second KILL; internal checks require the complete audit within 120 seconds. Wrapper counts explicitly treat the band model as a composition of per-band likelihoods. Configured position distances are quoted only from the already sealed earlier report and are not used to choose any audit state.
