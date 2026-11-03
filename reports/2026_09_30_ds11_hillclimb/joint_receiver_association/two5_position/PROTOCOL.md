# Newly validated 2.5MS/s positioning pilot

Freeze all six target records selected by exact acquisition family: family0
original15,30/additional11; family1 original24,31/additional9. Retain the known
additional9 original-IID qualification failure; do not substitute a different
record. Use the existing exact whole-source conditional receiver model with
the unchanged family0/1 coefficients validated in extra_donors. Its Doppler-only
arm is the control. Candidate mixtures, raw ownership alternatives, orbit banks,
observations and bounds remain unchanged. This repeats the pre-existing
estimator on newly supported settings, not a newly calibrated physical detector.

For each arm and record, run two starts: qualified original IID and center;
if original IID is unqualified, use center and center with timing+2seconds.
Do not use unqualified original coordinates as a seed. Require successful fit,
bound margin>=0.001, max gradient<=0.01, finite-difference discrepancy<=0.02.
Select highest qualified training score before held/geographic scoring.
Check exact zero-receiver-factor partition parity and signed gradient on all
records before fitting. Preserve every failed start and incomplete record.

Report all six outcomes and paired comparisons against contemporary Doppler
and available qualified original IID. Each family advances only if both arms
qualify on all three records, signed wins at least2/3 against the contemporary
Doppler control, its median error falls at least5%, itsP90 is no worse, and its
additional recording improves. No family/strength/seed is chosen by reference
error. Passing is a small exposed-site pilot, not broad accuracy confirmation;
any later deployment policy requires a separate whole-panel audit. Keep zero
height and causal orbit inputs primary, with no new RF. At most three workers,
each<=90seconds. The unsurveyed roof coordinate is used only after selections
are sealed; do not use it in model construction or optimizer selection.
