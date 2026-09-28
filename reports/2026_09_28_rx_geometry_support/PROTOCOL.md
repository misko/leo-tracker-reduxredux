# Descriptive geometry identifiability audit

The joint geometry model failed to improve transfer to the reused evaluation panels. Before changing its functional form, diagnose the information contained in its calibration geometry. This audit fits no model and changes no dataset or evaluation criterion.

Use only six calibration recordings' reception observations from the original pilot dataset and its saved feature transformation. Exclude the old other-catalogue component; normalize retained nomination log priors. Probability weights here are descriptive and may underflow for negligible nominees; they do not replace the log-domain scientific likelihood or alter nomination priors.

Give each recording equal total weight; within a recording weight exact lanes equally, within a lane weight reception windows equally, within a window weight nominees by their frozen conditional priors and receivers equally. Calculate overall weighted moments of saved standardized geometry features (up, north, east, differential east tilt and differential east×up tilt).

Split variance into within-time and between-group terms for groups defined by exact lane, nominee and receiver. A fixed feature within such a group can distinguish receivers or nominees but supplies no within-sequence timing variation. Report the exact variance identity, temporal fraction, global and within-time covariance eigenvalues, and correlations between differential tilt features and the receiver indicator. Do not equate nominal matrix rank with practical identification.

For each calibration lane, report window count, timestamp span, prior-weighted first-to-last LOS angular displacement and temporal geometry dispersion. The displacement is a forecast quantity, not observed satellite motion or emitter identity. Small values can explain weak temporal discrimination but cannot prove that all useful geometric evidence is absent.

Also report retained nomination prior entropy, effective count exp(entropy), maximum mass, number of finite log priors and number of weights at least 1e-6. Record per-nominee first/end LOS and their difference where available. This checks whether diverse travel hypotheses remain available to a geometry likelihood, rather than assuming a retained shortlist offers meaningful alternatives. Do not flatten or change these priors in this audit.

Separately inspect pose provenance and whether the nominal ±10-degree east/west representation is supported for the selected historical recordings. Distinguish fixture geometry, world orientation, cable mapping and the population actually analyzed. Missing metrology must not be replaced with invented measurements.

Test weighted variance decomposition, static/changing trajectories, weight normalization and exclusion of calibration-held/evaluation outcomes. Freeze code, tests, protocol and dataset/model hashes before computing. Use one thread, nice19, 4GiB, maximum60seconds. No RF, raw IQ or QNAP writes. This is post-outcome descriptive diagnosis, not a new positive test or permission to tune on evaluation outcomes.
