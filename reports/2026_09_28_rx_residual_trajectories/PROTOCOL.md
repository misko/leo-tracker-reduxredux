# Frozen residual trajectories

The preceding alignment diagnostic found sharply reduced support for saved
nomination frequencies in later windows. This descriptive stage preserves those
forecasts and examines signed nearest-candidate residuals across the temporal
boundary. It does not fit corrections, select nominations using later outcomes,
or interpret a nearest candidate sequence as a physical satellite track.

Use all calibration lanes of the original geometry dataset: six recordings,
twelve lanes, both reception and held-frequency roles. Exclude evaluation lanes.
Verify the preceding alignment evidence index and bind its dataset hash before
execution. Export every retained nominee, excluding the `other` component, with
normalized retained log prior and prior mass. No pruning changes inference.

For each window, nominee and receiver, compute observed-minus-forecast signed
nearest periodic residual in [-period/2,period/2). Resolve equal-distance ties
by saved candidate order. Empty candidate sets yield missing residuals. Preserve
candidate index/ID, forecast visibility, counts, role, source window and timestamps.
Elapsed time is relative to each lane's first reception observation.

Export circular changes in selected observed frequency, forecast frequency and
residual between adjacent windows where both receiver observations exist. Preserve
time gaps. These increments can include nearest-candidate switches and alias wraps;
they are not unwrapped Doppler slopes or verified continuity. Summarize the exact
last-reception/first-held pair for every nominee and receiver.

Per nominee and receiver, report each role's observed-window fraction, visible
alignment fractions within 500 and 1500 Hz (empty or invisible contributes zero),
and median signed/absolute residual conditional on observed candidates. Medians
are descriptive on the chosen circular branch, not a fitted frequency correction.
No decision threshold is tuned on outcomes, and no causal drift/handoff label is
assigned automatically.

Plots may limit emphasis to prior mass >=1e-6, declared explicitly, but the results
must retain every nominee and both receivers. Inspect source provenance separately
for deterministic role-specific mapping, candidate-selection or forecast changes.
Run component tests, then one single-thread diagnostic bounded to 120 seconds and
4 GiB. Use the existing derived corpus only; no RF collection or QNAP writes.
