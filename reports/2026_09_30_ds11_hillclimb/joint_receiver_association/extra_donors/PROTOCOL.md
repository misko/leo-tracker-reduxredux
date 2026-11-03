# Close missing 2.5MS/s donor eligibility evidence

The previous acquisition calibration lacks separate validation for families0/1.
Inspect the first four chronologically eligible captures from the33 previously
listed candidates. Selection requires exact radio, paired receivers,2.5MS/s,
qualified timing, no recorded exclusion, and both capture end and finalization
before the earliest DS11 start. Do not choose by DS11 or donor geographic error.
Bind the public TrackingInput manifest and current analysis manifest, project
stored candidates, reconstruct trajectories with minimum span3s/support6, and
report exact RF coverage and retained track counts per receiver. A frequency
subset is not an exact acquisition-family match. This is metadata/trajectory
eligibility only; orbit support, identity, detector calibration and analysis
availability still require verification before treating a recording as a donor.
No raw IQ reading or new RF collection. Preserve unsuccessful children. Limit
each child to90seconds and at most three concurrent single-thread workers.
