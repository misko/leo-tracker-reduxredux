# Differential receiver drift: correction preparation

This stage implements and measures coverage of a correction before geographic
fitting. It reads the frozen frequency-coherence census, alignment result, and
their bound exported observations. No candidate bank or roof coordinate enters.

Keep the published training-selected one-to-one pairs. Recompute each donor's
median RX0 minus RX1 frequency from training values. Fit the published drift
model with at least four other pairs in the same scan/channel/exact RF. Preserve
its polynomial qualification, rank/condition gates and ±20 Hz/s rejection bound.
The target response is omitted from the coefficient fit, but was used in the
earlier pairing selection; this is not independent identity validation. No held
coverage or outcome gates application.

For qualified pairs, subtract alpha * drift * (time - donor reference time)
from RX0, and (alpha - 1) * drift * (time - donor reference time) from RX1.
Alpha is fixed at 0.5 (symmetric), 0 (RX0 anchor), or 1 (RX1 anchor).
Also retain an exact unchanged control. Do not remove the fitted constant:
track constants cancel in the planned contrast likelihood. Apply the linear
correction at all observations of each qualified target track, including times
outside the donor centers' range. This extrapolation is a model assumption,
not an interpolation guarantee. Never transfer a correction across scans or RF.

Keep every track and observation; no pair, an unqualified calibration, or an
anchored receiver leaves its original frequencies intact. All arm comparisons
must retain these fallbacks. Pair-specific omitted-target coefficients are
cross-validation corrections, not a single measured hardware clock curve.

This preparatory census reports all 4,335 exported tracks, including seven that
the existing candidate banks exclude. Geographic coverage must separately use
the original 4,328 eligible tracks. Verify coefficient parity with the published
alignment result before reporting coverage. Test synthetic recovery, swap
symmetry, unchanged controls, held isolation, omitted-target calibration,
binding failures and the unidentifiable common drift. No geographic estimate
or sub-km accuracy claim is produced by this stage.

Further integration must use identical original training masks and candidate
banks, preserve the eighteen existing panels, replay the unchanged objective,
and freeze starts and numerical audits before any fits. Allocation assumptions
must all be reported, never selected by reference-coordinate error.
