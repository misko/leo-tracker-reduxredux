# Acquisition-specific conditional calibration

Before fitting, fix eight independent acquisition-family models and retain all
results. Use the chronological calibration/validation donor split in the inventory.
Fit receiver-only, elevation and signed west/east models using the existing
conditional three-state likelihood and 10-degree nominal outward antenna tilt.
Each family has eight receiver/RF intercepts; geometric arms add one shared
nonnegative slope. Bounds are intercepts ±20 and slope [0,40]; Gaussian prior
scales are 5 and 10 respectively. Fit only training-mask rows in calibration
donors. Keep inferred source labels, exact RF sets, and known nonempty RX states.
The calibration geometry already uses donor training data from both roles; this
is conditional receiver transfer validation, not a blind pipeline test.

Use zero and slope-five starts; select by penalized calibration objective.
Qualification requires solver success, projected gradient ≤0.01, and central
finite-difference discrepancy ≤0.0001. A bound-active geometric slope is allowed
and reported, because zero slope is a meaningful nested model.

Evaluate validation donors only on their held visit masks. Freeze controls to
receiver swapping and deterministic same-RF source-LOS permutation (seed
20260930), without refitting. A family passes only if all three fits qualify,
signed total held score beats receiver-only, elevation and both controls, and
signed beats receiver-only for strictly more than half the validation source
groups. Count groups by donor plus physical NORAD/RF, not by fragments.
No validation donors means unvalidated, never a pass. Report per-donor scores
and source win counts alongside pooled family totals. These are correlated
opportunities, not independent position-error trials.

This is a prerequisite screen, not a position improvement result. No DS11
position errors, orbit corrections, reference-dependent tuning, or coefficient
reuse from the older availability-ineligible calibration enter the fits.
Conditional evidence continues to omit 00 states; full-scan states are saved
for a separately specified activity/detection model. At most three workers,
90 seconds per family. Preserve failures and all family results.
