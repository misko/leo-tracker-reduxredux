# Position information and receiver geometry

## Finding

A finer search with the current model does not demonstrate a better position. A 5-by-5 training-selected grid, spanning +/-10 km around the Sacramento estimate, prefers a point 7.78 km from the reference rather than the original 5.79 km point. Held-out predictive NLL improves from 7.9823 to 7.6503 at the farther point. Better fit is not yet a dependable proxy for better position.

This diagnostic freezes the Sacramento branch's own shortlist throughout the local grid. No reference/Reno candidates enter it; the ground-truth point is scored only afterward. This is a conditional local diagnostic, not a complete full-catalogue search. The grid spans only 20 km in each direction, at 5 km spacing. Distances for new grid points use a spherical approximation. Sacramento-center score reproduces the earlier result to 9e-16.

## Evidence strength

- 2,745 observations in 58 tracks; 879 held-out one-second blocks.
- Median track span 27.52 seconds; longest 52.75 seconds. Median occupied-second count 23.
- 515 second bins contain both training and held-out observations. Scores therefore do not provide an independent future-time test.
- At the Sacramento position, 15/58 highest-posterior timing corrections exceed +/-5 seconds; 7/58 exceed +/-30 seconds; range -40.6 to +59.5 seconds.
- Median held-out RMS at the training MAP identity/time is 113.85 Hz; 90th percentile 399.83 Hz, maximum 995.60 Hz. These are diagnostics of the selected MAP component, not the predictive mixture's RMS.
- The input UTC bracket is 0.36545 seconds wide. Tens-of-seconds fitted shifts cannot be explained by that bracket alone; they may represent orbit error, wrong association, track construction, or model mismatch.

The independent-candidate Sacramento-versus-reference comparison is unstable to track composition. Sacramento's total log-score advantage is 108.19; track `e74b00af…` alone contributes 111.81. Removing that track reverses the ranking. This is a leverage diagnostic, not a justified exclusion. That RX0 track spans 40.83 seconds, has 63 observations, selects satellite 63869 with tau +26.1 seconds at Sacramento, and retains 241.91 Hz held-out RMS. A near-one assignment posterior does not establish its identity.

A descriptive bootstrap over tracks gives a reference-minus-Sacramento predictive log-score-per-block 95% range of [-0.553, +0.339]. Zero lies inside it. Tracks may share satellite/receiver errors, so this is not a calibrated location confidence interval.

## Receiver disagreement

With each site's original independently generated candidates, RX0 (31 tracks, 517 test blocks) favors Sacramento by 240.87 total log-score units; RX1 (27 tracks, 362 blocks) favors reference by 132.67. This conflict is not visible in the pooled score.

With the fixed Sacramento candidate set used for the local grid, RX0 selects (east 0, north -5) km from the Sacramento estimate. RX1 selects (east +10, north -10) km, on the grid boundary and about 18.8 km from reference. A boundary result is not a resolved optimum. These differences motivate checking receiver-specific bias and which satellite/track geometry each receiver actually contributes; they do not by themselves prove hardware bias.

## What geometry is available

The source radio is `radio_pluto_5d4d`. Its geometry/placement record is `deploy/station/gauss-r20-roof-20260926-v1.json`, valid before this scan. It records:

- nominal mount separation 0.08 m and outward tilt 10 degrees;
- east/west pointing with provisional software-to-connector mapping;
- null RF phase-center baseline in ENU, unmeasured RF phase centers and world tilt;
- roof location 37.849056280893684, -122.48575489722863, roughly 9 m from the older reference coordinate, with unknown altitude and survey uncertainty.

That absolute placement is evaluation evidence, not a permissible inference prior when evaluating unknown-location recovery. The roughly 9 m reference discrepancy is far smaller than the kilometre-scale error here.

The current Doppler evaluator uses one geodetic receiver point. It does not consume relative RX baseline, pointing, measured differential phase, or amplitude-ratio calibration.

For scale, an ideal 8 cm baseline permits at most 0.08/c = 0.267 ns geometric delay. At 11.2 GHz it spans about 2.99 wavelengths, so differential phase can carry angle information but is phase-wrapped. For an illustrative 550 km range and 7.5 km/s transverse speed, the first-order differential Doppler scale is only about 0.04 Hz, far below the residuals above. These are geometric scale calculations, not measurements from this scan. Phase-based angle information requires the same signal at both receivers plus calibrated differential phase/LO behavior, RF phase centers, and world orientation. Mount geometry alone does not supply those measurements. Pointing could supply probabilistic gain evidence after calibration; it should not be treated as a hard satellite visibility mask.

One suspected issue was checked and ruled out: the predictor uses 11.2 GHz while the recorded RF channels differ, but trajectory construction already scales measured frequency to the same 11.2 GHz reference.

## Recommended next model

Retain site-independent candidate generation, but connect observations that share physical causes:

1. Establish same-signal track links across receivers and visits using training-only timing/frequency/pilot evidence. Keep ambiguous links soft.
2. Fit one orbit perturbation per satellite and a shared capture-clock correction informed by its 0.365 s bracket. Include calibrated receiver/channel frequency offsets and slowly varying receiver drift. Avoid an unconstrained polynomial for every track, which can also absorb the location information.
3. Calibrate measurement noise and dependence from repeated observations, then use a normalized robust residual likelihood. Track count or duration alone should not imply independent evidence.
4. Check receiver-split and blocked-time predictions, then run the location search independently from both original geographic priors. Report position error only after each search is frozen.
5. Add calibrated differential phase or receiver gain-ratio evidence when its prerequisites are demonstrated on the recorded data.

This offers a plausible route to improved accuracy, but no closer estimate has been recovered by the present diagnostic. The previous report's improvement over the frozen probabilistic control also changes timing sharing as well as assignment treatment, so it cannot be attributed exclusively to soft association. The deployed capped-RMS baseline already preferred Sacramento.

Artifacts: `diagnose.py`, `diagnosis.json`, `plot_diagnosis.py`, `local_grid.png`. No production model or external scan data was changed.
