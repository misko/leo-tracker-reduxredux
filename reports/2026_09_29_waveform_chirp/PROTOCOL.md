# Frozen local frequency-rate forecast

Use the same eight cached visits and both receivers as the block-frequency-support experiment. Retain all five disjoint ten-frame blocks starting at frames 30,40,50,60,70: 80 blocks. Fit using only symbols 22–221 in the first eight frames. Compare constant frequency with a linear frequency evolution, profiling separate static complex gains per training frame/carrier. No inter-frame phase coherence is assumed.

Initialize constant frequency from an 8192-point training FFT and local scalar refinement. Initialize the linear model there with zero rate; optimize scaled intercept and rate with bounds ±1500 Hz around that frequency and ±100,000 Hz/s. Retain numerical failures as explicit baseline fallbacks. These wide bounds test the local model rather than assert physical oscillator or satellite limits.

Forecast the last two frames' frequency without using their frequency estimates. For each target frame and each arm, calibrate static complex gains using only symbols 22–121, then score symbols 222–301. Include the intra-frame quadratic phase in the linear model. All 160 target receiver-frames remain in scoring, including unsupported frames. No support threshold, satellite or position truth chooses a model.

This is acquisition-assisted prediction on previously examined data, not blind acquisition or absolute Doppler validation. Report per-visit paired NMSE changes, optimizer status, rate range, and frequency changes. Promote neither estimator on a few isolated improvements. No new RF, archive export, geographic fit or production edit.
