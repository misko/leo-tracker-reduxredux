# Causal joint orbit uncertainty: two-scan geographic pilot

Freeze scans 0 and 16, the DS7/DS8 coefficient priors, causal original/older
banks, source grouping, common physical candidate intersections, observations,
training masks and timing support from the numerical and prediction audits.
Primary arm is orbit; zero and matched linear-direction arms are controls.
Use the existing profiled-CFO Student-t4/100Hz objective. No newer orbit records,
coefficient tuning, candidate pruning or reference-centered regularization.

Two starts per scan/arm: original IID endpoint and (0,0,0). Twelve processes,
each capped at 90 seconds, at most three single-thread workers. No retries.
Existing L-BFGS-B settings and endpoint qualification apply: successful finite
interior endpoint, gradient maximum <=0.01, finite-difference discrepancy <=0.02.
Retain every failure and timeout. This small start set cannot prove global
optimality. Select each arm's highest qualified training objective and seal
all selections before geographic evaluation; never compare scores across arms.

Advance only if all six selected outputs qualify and orbit position error is
lower than original IID, zero, and linear controls on both scans. The reference
is used only for this final gate. Report all arms even if the gate fails. This
exposed two-scan pilot is not deployment validation or a calibrated uncertainty
claim. No offline orbit result belongs in the primary causal comparison.
