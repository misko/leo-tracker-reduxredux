## Purpose and experimental design

This comparison asks whether orbit-blind GLRT refinement, a learned receiver cone prior, and the V16 position score improve localization over the original T1-AT position score on recent recordings. It uses 16 fixed scans, eight at 2.5 MS/s and eight at 10 MS/s. Each scan is localized independently. No RF recording is started by this analysis.

The eight combinations of refinement off/on, cone off/on, and T1-AT/V16 each receive two final RF-calibration arms: fitted `c` and `c = 0`. There are therefore 16 position fits per scan and 256 planned fits. The cone toggle affects final position scoring, not the discrete satellite-selection procedure. Both position models share full-data calibration and the T1-AT greedy-plus-replacement association engine. T1-AT here denotes the original Gaussian position score C0, not a replay of historical calibration-fold experiments.

The cohort was fixed by recording metadata rather than localization outcomes. Eight equally spaced time targets per sample rate were matched to the nearest unused eligible completed capture in the eight-hour request window. Each recording lasts 300 seconds. The different-rate scans are not simultaneous controlled observations of identical signals; rate-stratified results are descriptive, not a causal estimate of a sample-rate effect.

## Receiver geometry and its uncertainty

The capture metadata binds the LT3D-004B fixture, with a nominal 40-degree included feed-axis angle and 20-degree outward tilt per holder. RX0 is nominally west-facing and RX1 east-facing. A level base implies nominal 70-degree elevation. These are configuration and fixture facts, not a surveyed measurement of the installed RF boresights. Actual elevation, polarization roll, and phase-center baseline were not measured; the physical connector mapping remains provisional. The known roof coordinates are operator supplied, with unknown survey uncertainty and altitude datum.

The cone model uses shared shape with receiver-specific roll, learned on 20 earlier scans disjoint from this cohort. It applies a soft preference for the receiver that made a detection. It does not treat absence on the other receiver as a veto, and unsupported sky regions remain neutral. This avoids equating west-facing hardware with a perfect western-hemisphere exclusion.

## From recorded IQ to one observation per window

The original analyzer evaluates 20 ms GLRT probes at a configured 120 ms probe stride within retained adaptive visits. It permits up to eight acquisition candidates and uses a saved GLRT margin cutoff of 0.025. A window is identified by probe, receiver, and RF channel. Multiple candidate records within one window are alternative frequency/epoch hypotheses, not independent 20 ms recordings.

The original branch keeps the highest original GLRT-margin candidate per passing window. The refined branch re-evaluates candidates against recorded IQ using candidate-guided frequency and epoch refinement without orbit input, then selects the highest refined-score candidate. Failed refinements retain their original estimate and are counted in the refinement receipts. Frequencies are compared with the known 4.4 microsecond pilot alias period, approximately 227.273 kHz.

The refinement performs three bounded iterations. The first checks the saved frequency and its two neighboring alias centers at the saved epoch. Later iterations refine fractional epoch around the current best estimate and recenter frequency. A trial must return finite scores and remain within 1 kHz of its center modulo the alias period; the largest GLRT margin wins, with the previous best retained as a candidate. This uses IQ evidence rather than nudging measurements toward an orbit prediction. It is not an exhaustive search for new signals that were absent from the original candidate list.

Refinement can change both a candidate's frequency and which candidate wins a window. Consequently the original/refined comparison measures the total downstream effect of refinement and winner selection, not merely a frequency correction applied to an otherwise fixed dataset. Calibration and satellite selection are rerun separately for the two branches.

The final position fit uses all associated top-one windows in that branch. It does not use every raw candidate, and it does not include unassociated windows as additional negative evidence. GLRT margin selects a winner but is not itself the final likelihood weight. Every retained observation has unit weight before soft satellite/clutter responsibilities are computed.

## Calibration and satellite selection

Calibration uses the full scan at the known roof, with receiver offsets, drifts, a smooth receiver baseline, RF dependence, and satellite timing. Initialization uses track shapes and multiple timing starts; it does not transfer a previous scan's estimated position. Calibration must pass its convergence checks before downstream association is accepted.

The association stage searches the visible candidate bank with satellite timing bounded to plus or minus 20 seconds, a 600 Hz matching tolerance, and at least ten supporting peaks for a candidate. Greedy additions are followed by removal and replacement passes. Its discrete selection objective is:

`association score = number of assigned windows − 10 × number of selected satellites`.

This is distinct from the final probabilistic localization loss. A larger association score or a higher coverage fraction does not by itself establish more accurate satellite identities or position.

Within each original/refined branch, fitted-c associations determine a frozen set of observations, satellite trajectories, and receiver baseline. All position-score, cone, and final RF arms use those same inputs. Thus the final `c = 0` arm tests removing the additional RF coefficient at positioning; it is not an end-to-end pipeline in which RF dependence was forbidden during upstream calibration and selection.

## Final position model and loss

After subtracting the fixed receiver baseline, the predicted frequency for observation i and satellite s is:

`prediction(i,s) = orbit_Doppler(s, x, t_i + tau + delta_s, F_i)`

`                 + a_RX + b_RX × (t_i − 150 s) + c × (F_i − F_ref) / 1 GHz`.

Here x is horizontal position, tau is a common orbit time shift, delta_s is a satellite-relative time shift, and a_RX and b_RX are additional receiver offsets and linear drifts. The coefficient c is learned in the fitted-c arm and fixed to zero in the other arm. Doppler is evaluated at each observation's RF frequency.

The final loss is a conditional finite-set likelihood rather than fixed-owner least squares. Each retained window can share soft responsibility among the selected satellites and clutter. Only the selected satellite set participates, so a discarded catalog alternative cannot receive responsibility in this final fit.

For window g, let q_gs be the detection probability, A the alias period in Hz, phi_A the alias-aware Gaussian frequency density, and lambda the clutter rate. The singleton likelihood can be written:

`P0_g = exp(−lambda) × product_s(1 − q_gs)`

`H_g = lambda / A + sum_s[q_gs / (1 − q_gs) × phi_A(residual_gs; sigma)]`

`L_g = P0_g / (1 − P0_g) × H_g`.

The minimized objective is:

`J = −sum_g log(L_g) + 0.5 × (tau / sigma_common)^2`

`    + 0.5 × sum_s(delta_s / sigma_relative)^2`.

Without cones, q_gs equals the model's detection budget divided by the selected satellite count, multiplied by the existing hard visibility gate. With cones, a support-aware receiver preference tilts those probabilities while preserving the window's total detection mass. Cone strength is 0.5 and the probability floor is 0.1. The hard horizon rule is identical in both arms: the comparison does not simultaneously replace it with a smooth horizon model.

| Setting | T1-AT original score C0 | V16 |
| --- | ---: | ---: |
| Frequency Gaussian sigma | 200 Hz | 125 Hz |
| Detection budget | 0.8 | 1.6 |
| Clutter rate | 2 | 0.5 |
| Common timing prior sigma | 10 s | 3 s |
| Satellite-relative timing prior sigma | 1 s | 0.15 s |
| Common timing hard bound | ±10 s | ±10 s |
| Total satellite timing hard bound | ±20 s | ±20 s |
| Horizontal search radius | 4 km | 4 km |

Analytic gradients include frequency residual derivatives with respect to position, timing, receiver terms, and c. The cone arm also differentiates its geometric preference. Its zero-strength score/gradient parity and nonzero finite-difference derivatives are tested. A Fisher approximation preconditions optimization; it is not a certificate that a nonconvex search has found the global minimum.

## Search budget and convergence

Every final arm receives fresh association-timing and zero-timing roof starts, four cardinal probes at 3.2 km, and three local starts comprising the roof fit and the two best probes by objective. The roof-start budgets are 5 seconds each; probe budgets are 1 second each; local starts receive 8 seconds each; polishing receives 15 seconds. Unconverged solutions can additionally receive 20 seconds of SLSQP and 10 seconds of Fisher continuation. These are matched maximum budgets, not guarantees of identical iteration counts on a shared host.

Solutions are selected by their own objective, never by proximity to the known roof. A saved fit is converged only when its checked constrained stationarity measure is at most 0.001 and position was not fixed. A result at 4 km is a boundary solution, not an unconstrained minimum. Converged interior solutions can still occupy different local basins.

Execution batches have wall-clock limits separate from these numerical budgets. An interrupted batch is pending work, not a scientific result. Completed arm files are retained; refinement resumes from visit checkpoints. The report counts saved, converged, boundary, and missing cases separately.

## Interpretation and limitations

Position error is horizontal distance from the best-found location to the reference roof. Coverage is assigned top-one windows divided by passing windows from that measurement branch. Posterior-weighted frequency RMS describes fit quality, not absolute localization accuracy. These quantities answer different questions and are reported separately.

The paired effect of a switch is computed within the same scan with every other factor fixed. Negative position-error change means improvement. Comparisons exclude incomplete pairs, explicitly count unconverged pairs, and do not subtract medians from different available scan subsets. Repeated variants of one scan are not independent observations.

All calibration and position fits use their full designated data, with no holdout folds in this experiment. Upstream calibration and association are conditioned on the known roof. Therefore the position results are exploratory conditional localization diagnostics, not blind geolocation or held-out validation. V16 was developed on earlier scans, but this does not remove the known-location conditioning in the new pipeline.

A better in-sample frequency score cannot establish better position. Raw negative log likelihoods are also not comparable across T1-AT and V16 because the likelihood widths, detection/clutter parameters, and priors differ. The study should not declare a winning configuration until the fixed cohort has been evaluated and convergence limitations are included.

## Reproduction and evidence

The frozen `protocol.json` records the cohort digest, scientific source digests, settings, and search budgets. `results.csv` contains every planned position case, including missing ones. `paired-changes.csv` contains within-scan comparisons. Each saved fit links its exact input arrays, calibration and association receipts, optimization starts, objective, convergence diagnostics, and source hashes. The original and refined branch observations remain distinct.

Run `summarize_factorial.py` from the study directory's repository to refresh the figures, tables, and this report from saved results. `run_factorial_bounded.py` resumes missing position arms; `run_bounded.py` handles checkpointed export, orbit-bank, refinement, calibration, and association stages. Neither command requests new RF collection. The source files and scientific protocol must remain unchanged when resuming this experiment; a scientific change requires a separate version.

The factorial runner also accepts `--refinements original` or `--refinements refined` to schedule one measurement branch independently. This allows original-data comparisons to proceed while IQ refinement runs. It changes execution order only: the full report retains all 256 planned cases, and the other branch remains pending rather than being removed from the denominator.
