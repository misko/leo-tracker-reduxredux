# Next evidence needed

Cross-band candidate residual transfer is not promoted. No width, residual
threshold or shuffle should be tuned to improve these exposed results.

The next concrete prerequisite for a reception/non-reception geometry model is an
observing-opportunity audit. Inspect persisted scan visits for both receivers:
actual start/end times, tuning, active dwell, receiver presence and extraction
coverage. A missing track is negative evidence only when the relevant receiver
was observing the appropriate signal/band with usable data. Missing or incomplete
coverage must remain unknown, not non-detection.

Before implementing another likelihood, establish whether those opportunities
can be joined through public contracts to the existing 72 target scans and 186
donor scans. Report coverage by dataset and receiver, including tuning mismatch
and incomplete visits. Do not infer satellite identity from similar frequency
alone, or interpret RX0-before-RX1 as direction without a supported common track.

If opportunity evidence is sufficient, freeze a shared-pose soft detection model
with an explicit false-detection component and fit pose only on donor training
data. Compare nominal, swapped and co-pointed axes on identical held opportunities.
Keep location, detection prediction and association validation distinct. Only
advance to geographic fitting after predictive transfer beats those controls;
otherwise preserve the negative result and investigate independent calibration.

This is a proposal, not an executed detection model. Reliable sub-km performance
for DS7, DS8 and DS9 remains unproven.
