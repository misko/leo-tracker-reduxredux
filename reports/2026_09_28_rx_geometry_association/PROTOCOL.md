# Geometry association pilot: executable pre-fit choices

This is the first fitted comparison under the sequence follow-up design. It tests geometry-conditioned candidate association on the existing ten roof records. It is not full DS7 confirmation, physical direction calibration or a location-error benchmark. The broader goal remains improving association with receiver geometry.

## Scope fixed before execution

Keep the existing six calibration/four evaluation recording split, train/reception/held source groups, thirty selected tracks, three candidates per track, training CFO/alias/RX calibration and nominal RX0-west/RX1-east ENU axes. Build one common exact-lane paired-window population; all arms use identical rows. Invisible hypotheses have zero signal-detection probability, not missing rows. Include every passed raw candidate and qualified empty set without a residual gate. Preserve source IDs and explicit exclusions. No new RF or raw IQ.

Use one normalized mixture per lane over training-selected tracks (equal prior weight), each retained candidate (original finite training log likelihood normalized in log space, multiplied by retained catalogue mass) and a common omitted-catalogue clutter branch. Transform every frequency prediction and candidate into common RX0 coordinates with the frozen native receiver bias and RF scale. No future alias integer, CFO, frequency offset or satellite catalogue search is fitted.

## Pilot model fixed in advance

The earlier design's AR(1), mark discrimination, recording random effects and flexible clutter are deferred explicitly. This first comparison uses shared-window receiver dependence: five-point Gauss-Hermite integration of a common standard-normal logit perturbation, fixed SD=1, rho=0 in **every** arm. Time-varying geometry remains a reception feature; this is not an AR sequence result. Detector marks are preserved but treated as a common ancillary distribution, and scored frequencies/counts are conditional on those marks.

Clutter is a Poisson process with separate RX0/RX1 intensities and uniform density on the canonical alias circle. At most one signal candidate per receiver is superposed. Sum over all possible signal candidates; do not choose one. The periodic Gaussian signal density uses the central wrapped residual plus neighboring periods, valid for the fixed sigma grid 500, 2500 and 10000 canonical Hz and the recorded approximately 227 kHz periods. Retain all clutter/count normalization terms. The omitted-catalogue branch has signal probability zero.

Calibrate nuisance parameters using **only calibration reception windows**. Fit the D model for each fixed sigma; select the smallest penalized negative log likelihood, with smaller sigma breaking exact ties. Fit RX clutter log-intensities jointly (bounds -5 to 4, Normal(log(1.5),1.5) priors). Then freeze sigma and both intensities for all arms and controls. Initial intensities are 1.5. No calibration held or evaluation outcome chooses the nuisance model.

D has intercept, RX contrast (-1,+1), and log(sample_rate/5 MHz). S adds common LOS up/north/east. T adds nominal RX-signed horizontal boresight projection (+/-sin(10 degrees)*east) and its interaction with up. The common cos(10 degrees)*up part of the boresight is already represented by S. Centre/scale non-intercept features using calibration reception covariates only, including both receivers and all retained hypotheses. Freeze these transforms for evaluation and controls. The other branch is invisible and its dummy features do not enter standardization.

Use zero-centred Gaussian MAP priors: intercept SD=2, other D coefficients SD=1, S additions SD=0.5, T additions SD=0.35. Fit each arm with L-BFGS-B (maximum 60 iterations and 600 function evaluations), starting additional coefficients at zero. Record convergence; no unconverged fit is a verified comparison. Sigma grid selection and these caps are fixed before outcomes. Exact nuisance cancellation across arms does not justify dropping terms from absolute likelihoods.

## Evaluation and controls

Condition the normalized lane mixture on each evaluation recording's reception windows, then score each held window before consuming it; parameters stay fixed. The sum is a joint held-block log predictive density. Report score per unique paired window per record and equal-record mean contrasts T-D, S-D, T-S. Also export prior, reception and final component log weights so association changes are inspectable. Do not call them calibrated satellite identification probabilities.

Controls keep T coefficients and training priors fixed: swap only nominal receiver boresight signs; reverse time-sorted geometry within each lane/component/role, leaving frequency predictions, actual times and observations unchanged. Recompute reception filtering and held scoring for each control. T with its extra coefficients set to zero must reproduce S for identical nuisance coefficients. A positive feature result requires T to beat D and S and outperform both controls on the same held population. Report all per-record contrasts; four reused records are exploratory evidence.

## Execution

Test coordinate transfer, empty sets, duplicate-window rejection, candidate permutation, periodic density/alias invariance, shared-RX integration, log-prior recovery, filtering order and nested arms before fitting. Freeze code, configuration, source hashes and command. Dataset preparation and the fit are each serialized, one numerical thread, nice 19, 4 GiB address space, maximum 300 seconds. Preserve failures; do not tune the protocol after held results. Keep the goal active if predictive improvement remains unverified.
