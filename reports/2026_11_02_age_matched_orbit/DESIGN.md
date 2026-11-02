# Prospective age-matched orbital uncertainty experiment

This follows the [generalized correction experiment](../2026_11_02_generalized_corrections/README.md). ALGO07 remains deployed. The question is whether comparing historical forecasts at an age similar to the current nominal TLE produces a more useful uncertainty proxy than propagating every old TLE all the way to the current scan.

## Fixed comparison

Reuse the exact 205 available fast recordings and immutable ALGO07, numerical-repair A and previous causal-covariance B decisions. The old ledger contains 146 actual generic target nominations; no old capped ranking or failed numerical attempt is retried. New policies retain selected A where no supported new covariance is available. No satellite identity, native observation, graph join, ownership, alias or empirical likelihood weight changes.

New candidate fits use matched c=0 and fitted-c arms, the previous numerical solver and scientific gates, and the same original shared fitted-c RF starting position/reference within the existing regional box. Only the covariance construction changes. Both arms must qualify. There is no candidate selection by geographic error or by choosing the covariance that gives the best scan residual.

## Age-matched covariance

Let H be the nominal TLE's age at the native observation midpoint. A historical pair consists of an older TLE propagated to the epoch of a newer TLE, with forecast horizon h. Retain pairs with |h−H| ≤ max(2 hours, 0.25H). Both TLE epochs and recorded availability must precede the scan cutoff, and the older TLE must be available by the historical prediction target epoch. Preserve the existing 72-hour eligibility window and verified element/snapshot provenance.

Select a maximum-cardinality set of pairs without reusing elements. Among equal-cardinality sets minimize total absolute age mismatch, then use stable epoch/hash ordering. Pair selection cannot depend on orbital discrepancy, RF residual or position error. Non-reused elements do not establish statistical independence; shared satellite dynamics and catalog snapshots remain correlated.

Rebuild the physical mean-motion, inclination and RAAN derivatives around each newer historical TLE over the corresponding short observation arc. Align historical orbital phase using states alone and remove the phase tangent. Estimate innovations in physical parameter units, then map them into the current model's declared standard deviations. Do not project historical state geometry onto a current-epoch state matrix or copy standardized coordinates between unequal scales. Preserve the current model's mean-longitude reference convention.

Use the uncentered second moment with fixed 50% shrinkage toward identity, variance eigenvalue floor 1 and ceiling 16, zero prior mean, and the existing physical representation checks. The Gaussian normalization remains in the variational inference. No shrinkage hyperparameter is fitted in this experiment, so an age-construction change can be isolated from hyperparameter fitting. This remains a catalog-revision proxy, not calibrated orbit truth.

## Support policies declared before RF outcomes

The first metadata-only inventory, before requiring historical forecast availability, found maximum non-reused matching counts 0/1/2/3 on 48/55/37/6 of 146 nominees. Thus three pairs would cover only six cases and two pairs 43. This prompted a prospective coverage-based decision, before any new RF fit or geographic outcome:

- **Age3, primary:** require at least three non-reused pairs.
- **Age2, exploratory:** require at least two non-reused pairs.

Both use exactly the same covariance, endpoint and gates when eligible; Age3 is a strict subset. There is no second fit for the eligibility comparison. The stronger historical-availability check may reduce these preliminary counts and must not be relaxed after observing outcomes. Final support inventory and source seals are required before RF execution.

## Validation and execution

Historical revision prediction must build preprocessing, mode scales and history from material available at that historical forecast's issuance. A held newer TLE may supply a diagnostic outcome but may not set the predictor's scales or covariance. Randomize whole groups, retaining shared elements and snapshot dependencies together, with seed 20261102. If strict causal preprocessing or grouping leaves insufficient independent support, report validation as inconclusive. No future catalog revision may calibrate a prior applied to an earlier scan.

The RF run is bounded to eight BLAS-one workers and 1,200 seconds total, with unchanged 120-second model-arm limits. Candidate cases are fixed from the supported history inventory before launch. There are no automatic completion waves or retries. Preserve all partial stages, caps and unchanged fallbacks in the full 205-record ledger. Verify original input/objective/native ownership and immutable selected-A comparator parity without rerunning old ranking or solver decisions.

Seal and independently audit the full RF decisions before the root evaluates geographic errors. Report mean, median, tails, regressions, 500 m success fraction, unchanged association counts and matched c arms separately from frequency-fit scores. The cohorts have already influenced development and cannot establish independent new-site generalization.

A separate fixed four-case diagnostic compares the previous B results for DS26-0309, DS26-0307, DS26-0315 and FRSH-0004. Those cases were chosen after their outcomes were known; this diagnostic cannot train a gate or select a prior. No new position fits are authorized for it.

No new RF collection, production change or algorithm promotion is part of this experiment. The report, source and results will be published to remote main.
