# Next cone model: conserve probability mass when rejecting satellite explanations

Proposal only. Finish the two frozen arms before implementing or launching this
comparison. No cone-plus-trend accuracy or direction result is claimed here.

The previous cone factor multiplied satellite likelihoods, with a 1% floor.
When all candidates share a locally constant factor, that factor cancels out
of their normalized weights and held prediction; the track retains its original
frequency-based geographic force. The present explicit trend branch provides
a place for explanations incompatible with receiver geometry.

For K retained visible candidates, let q be the declared background prior and
g_k the training-track cone compatibility of candidate k. Define prior weights:

    satellite k: (1-q) g_k / K
    unassociated trend: q + (1-q) [1 - mean_k(g_k)]

They sum to one. This preserves the conditional-bank interpretation and does
not claim to recover omitted catalogue mass. All g_k=1 reproduces the current
mixture; all g_k=0 yields only the trend density and no frequency-based position
force. A common small constant g no longer simply cancels: it reduces the prior
mass of satellite explanations relative to the alternative. Position derivatives
must include the change in both satellite and background weights when g varies.

One position, fixed RX axes and fixed cone widths must apply throughout each
scan set. Each candidate retains a single trajectory throughout its track.
The declared 20/30/40/50 degree half-angle sensitivity arms can use the maximum
training boresight angle, with an explicitly stated edge function. A soft edge
does not enforce a literal hard cone; a hard edge introduces discontinuities
that need an appropriate optimizer and an unchanged audit policy. Do not quietly
describe one as the other or infer hardware beamwidth from reference errors.

For normalized conditional held-frequency predictions, the training-derived
weights must remain fixed in the full/training density ratio. Held angles can
be reported as a separate predictive geometry audit, but cannot silently change
training weights. Scoring reception/non-reception as part of the likelihood
requires an observation space including absent detections and a consistent
joint detection model; that is not supplied by this formula.

Before fits, independently verify weight normalization, both neutral limits,
common-factor attenuation, derivatives including background-weight changes,
held-data isolation, and receiver-swap/identical-axis controls. Keep all fixed
panels and the no-cone mixture as the control. Model-based cross-RX association
and travel direction remain unverified until independently tested. The assumed
world pose and provisional receiver mapping remain separate limitations.
