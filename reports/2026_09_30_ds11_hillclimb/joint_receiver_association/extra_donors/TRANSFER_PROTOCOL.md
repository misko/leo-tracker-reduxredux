# Frozen receiver-coefficient transfer to extra donors

Do not refit existing acquisition_calibration/fit-0.json or fit-1.json. Keep
the qualified N23 station east/north estimate and zero-height convention.
For each of the four exported donors optimize only timing in[-5,5]seconds,
with starts0,-2,+2, retaining complete candidate mixtures and per-track CFOs.
Use training likelihood only. Require successful finite fits, bound margin
>=0.001s, timing gradient<=0.01 and independent finite-difference discrepancy
<=0.02. Select the best qualified training score; preserve every failure.

Using the selected timing, reconstruct the pinned newest-per-object catalogue,
require exact bank replay for selected candidates, and retain training MAP
identities only at posterior>=0.9. Export the existing source-bit/ownership
semantics and source/RF line-of-sight geometry for every observation window.
These are conditional track-retention events, not calibrated physical absences.

Evaluate each frozen receiver/elevation/signed model on held visits. Keep the
existing receiver-swap and within-RF geometry permutation controls and the
existing conditional screen: signed total held score exceeds every control and
strictly more than half of source/RF groups improve against receiver-only.
Require the screen separately on both new recordings of a family before any
DS11 positioning pilot. This is distinct-record transfer, not a chronological
forward validation: some new recordings precede the original fitting donor,
but their recorded analysis is available before DS11. No reference coordinates,
DS11 residuals or geographic errors enter this stage. Preserve all denominators
and unsuccessful donors. Each child<=90seconds, at most three concurrent workers.
