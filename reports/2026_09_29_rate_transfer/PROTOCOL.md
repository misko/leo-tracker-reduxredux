# Donor-calibrated shrinkage of waveform frequency rate

Following the adverse unrestricted-rate result, freeze correction strengths 0, 0.25, 0.5, 0.75 and 1. Strength zero is the constant model; one is the unrestricted model. Interpolate both frequency intercept and rate between these endpoints, recalibrating nuisance gains on the same target early symbols for each arm.

Use first-30-frame blocks (starts 0,10,20) for calibration. Each block fits its first eight frames and forecasts its last two using the preceding chirp model unchanged. Select strength separately for each target dataset, excluding that entire dataset and using only donor calibration blocks. Minimize mean NMSE with equal donor-dataset weight, equal visit weight within dataset, and equal block/receiver/target weight within visit. Exact ties choose smaller strength.

Freeze that strength for the target dataset's five evaluation blocks (starts 30,40,50,60,70). All 80 evaluation blocks / 160 receiver-frame targets remain. Replay zero and one against prior results. Report selection curves, fit qualification, target predictive errors, and no location claim. This follow-up is explicitly motivated by already exposed results, so held-out computation is not research-blind validation.
