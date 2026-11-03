# Does RX-difference scale predict individual and shared residuals?

Reuse exactly the 1308 matched track pairs and their training-only features from the completed RX-difference calibration: 953 donor pairs in DS7–9 and 355 DS10 target pairs. Reconstruct identical mutual-nearest within-one-microsecond observation pairs and masks; assert inherited difference residuals, feature and support match.

For each pair form RX0 residual, RX1 residual, and their arithmetic mean. Subtract each channel's own median over the both-training observations, then score its both-held residuals. Do not remove slopes or use held values in centering. These are candidate-conditioned model residuals, not measured absolute CFO errors or isolated white noise.

For each of the three channels, fit a constant Student-t4 scale and a log-linear function of the inherited RX-difference MAD feature using only DS7–9, with the same equal-dataset/equal-scan/within-scan observation weights, bounds, optimizer options and qualification gates as the preceding calibration. Freeze these parameters before scoring DS10. Report each channel separately on exactly the same 7195 held target pairs; do not choose a favorable channel or tune hyperparameters. No geographic weighting or fit in this experiment.

Test shared-signal behavior and training-center isolation, verify source hashes and exact reconstruction, and cap execution at 180 seconds. No new RF, export, propagation, production changes or silent retries. These exposed datasets do not constitute research-blind validation.
