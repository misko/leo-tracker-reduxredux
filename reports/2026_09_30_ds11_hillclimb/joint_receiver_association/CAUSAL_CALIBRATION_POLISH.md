# Stationarity continuation of availability-correct geometry

The N23 fit terminates successfully on relative objective change, but its raw
maximum gradient .0188737 exceeds the unchanged .01 qualification gate. Its
finite-difference discrepancy is 8.24e-6 and it is interior. Preserve this
unqualified result. One numerical continuation may start from that same
training-only endpoint, with the same N23 data, model, priors, bounds and raw
qualification requirements. Tighten only L-BFGS-B relative function tolerance
from 1e-13 to 1e-15; keep other optimizer options and the 90-second child cap.
Recheck all derivatives, require no worse training score within numerical
tolerance, and accept only if the original qualification gates pass. No held
data or reference position is used; no threshold is relaxed.
