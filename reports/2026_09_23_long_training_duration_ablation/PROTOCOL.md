# Frozen duration ablation

First six frozen long-TRAIN sessions only. For each minimum track span 10,
20, and 30 seconds and each original Sacramento-250/Reno-500 prior, fit uses
only each track's deterministic training mask. Reserved rows and the reference
coordinate are read only after every threshold/prior inference is sealed.

Reuse the published minimum-3-second baseline. Keep its score, grid levels,
candidate inventories, altitude zero, epoch zero, and beam width unchanged.
Report reserved RMS both on each selected duration subset and on fixed all-3s
support, with candidate identities and offsets chosen from training rows only.
Do not select a duration threshold from reference error.

An initial wrapper was stopped during review before completing a valid sealed
run: it mislabeled a returned training score and evaluated reserved rows before
the common seal. The corrected run writes exclusively to `sealed/`; any earlier
top-level results are invalid and excluded from scientific comparisons.
