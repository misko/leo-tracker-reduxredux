# Acquisition-aware model averaging

This is a new exploratory follow-up after observing DS7's loss under the broad
frequency prior. Reuse all 168 prior pilot frames unchanged. No outcome-based
window exclusion, new IQ, RF, catalogue or geographic scoring.

Retain the preceding Gaussian integrated-gain model, training-only power scales,
alternating even-Qin split and uniform -2000:10:+2000 Hz frequency grid. Add the
fixed acquisition residual zero as an explicit competing signal model. Compare:
1. acquisition/broad-frequency prior odds 1:1, no null;
2. acquisition/broad/null prior probabilities .25/.25/.50, retaining total
signal/null odds 1:1. Update weights using training evidence only. Do not tune
prior odds or select an arm using held/geographic scores. The broad grid includes
zero, so this is an additional point mass at zero, not disjoint support.

Replay the preceding five arms and report all paired held predictive scores,
with the new arms against fixed acquisition, ordinary point, broad mixture and
noise-only. Keep real and the same seeded scrambled controls separate. Report
posterior component weights and all original frames, including null-dominated
cases. These remain conditional empirical-Bayes model weights, not calibrated
RF identity or presence probabilities. Acquisition used the original probe,
including later-held symbols; the split is conditional on acquisition.

Known ±250 Hz post-demodulation injections have two cases: translate both the
grid and acquisition point by the known amount (coordinate invariance within
1e-8), or keep both fixed (report bias/ambiguity). For each new arm, a reliable
pair requires both model signal weights >.99 and original conditional signal
mass staying inside the shifted fixed interval >=.99. Report all-pair and
reliable-pair posterior-mean shift errors. No claim that the mean is a promoted
measurement. In the no-null arm signal weight is necessarily one; retain that
limitation when comparing coverage.

The necessary advance gate remains positive equal-window held gain versus
acquisition and noise-only on every dataset and maximum reliable shift error
<=5 Hz. A coordinate-invariant model can still be biased under a fixed prior.
If either criterion fails, do not substitute this estimator into positioning.
No post-result relaxation of the gate. No frequency or geographic accuracy claim.

Three sequential jobs, each 60 seconds, 2 GiB, one numerical thread, nice19.
No retries. Preserve commands, source/input hashes, all results and terminal
failures. Tests compare posterior averaging with joint/train evidence and verify
that held predictions do not mutate training weights. Independently reconstruct
all predictions from component joint/train evidence after execution.
