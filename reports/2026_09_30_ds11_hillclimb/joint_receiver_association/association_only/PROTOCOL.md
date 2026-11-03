# Freeze receiver geometry for association evidence

The acquisition-specific joint position pilot fails its fixed gate (3/11 wins,
worse medians/tails). Preserve it without selective retries. Test whether its
approximate receiver beam model is useful for satellite identity while its
direct angular gradient biases position.

Use the identical eleven-record panel, calibrated coefficients, exact source
assignment, candidate banks, CFO profiles, training/held masks and original IID
initial solutions from acquisition_position. Evaluate every candidate's RX
state probabilities once at that scan's original IID EN/time estimate, then
hold these probabilities fixed throughout optimization. Satellite-assignment
posteriors still update with Doppler and position. Do not freeze association
identities, prune candidates, weight-tune, or use reference coordinates. This
is a plug-in association model using the same scan's initial estimate, not a
fully joint generative angular measurement model or independent new sensor data.

Fit Doppler-only and frozen signed arms for all eleven records (22 cells).
Use identical EN/time bounds and qualification gates to acquisition_position.
Set L-BFGS-B gtol=0.001, ftol=1e-13, maxiter100, maxls25 for both arms. The
gradient stop remains ten times stricter than the unchanged qualification
gradient limit 0.01. This avoids chasing changes below floating-point resolution
seen in the preceding failed line searches; no failed cell is reclassified.
No selective retries. Each child ≤90 seconds, ≤3 single-thread workers.

Before fitting, verify frozen emissions do not change with candidate position
updates and audit full objective derivatives on original 0. Preserve exact
zero-receiver-information parity through the existing component tests.
Read position errors only after all terminal receipts exist. Apply the identical
cohort-separated gate: every cell qualified, at least 5% median reduction,
strict majority of wins, no P90 increase relative to both original IID and
refitted Doppler in each cohort. Failures/missing cells stay in the denominator.
A failure ends this fixed variant. A pass requires remaining controls and
broader eligible-record confirmation before any accuracy claim.
