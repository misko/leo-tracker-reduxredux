# Broad-prior acquisition: bounded follow-up

User authorization: implement the proposed likelihood diagnostics, Gaussian
mixture reduction and adaptive spatial map with concurrent SOL agents. Preserve
the previous 64-scan experiment and its source hashes unchanged.

Reuse its exact selection (22 DS9, 21 DS10, 21 DS11), pre-association measurements,
causal orbit catalogues, conservative source-overlap exclusions and chronological
track ordering. Each recording resets all inference state. No new RF collection,
raw-IQ processing or reference-directed satellite shortlist.

The first eight selected DS9 recordings are development cases in chronological
order. Begin diagnostics with the first two and at most eight retained tracks
each. Reference-location diagnostics are explicitly labeled oracle diagnostics;
they cannot supply location or identity initialization to blind runs. Synthetic
tests establish mixture reduction and spatial refinement behavior before real
replay. Freeze numerical settings before the regression panel. The existing 64
recordings have been inspected and are a regression panel, not a fresh holdout.

All blind spatial priors use the Sacramento center (38.5816, -121.4944) and
250 km intended radius. The Gaussian arm retains the earlier 32-cell approximate
uniform disk. The map must declare its cell/quadrature representation and any
conditional nuisance simplification; differing nuisance models prohibit a
matched superiority claim.

The initial merger experiment materializes at most 128 children using the
existing normalized whole-track likelihood, then reduces to 32 Gaussian
components. Report both pre-reduction discarded probability and distributional
distortion from merging. The old >1% discarded-probability gate remains. A
projected merge score is a heuristic, not a full-joint KL certificate. Joint
means and covariances, including nuisance cross-correlations, are moment matched.
The larger temporary bank is disclosed separately from the retained-state cap.

Run no more than two real numerical workers globally, one numerical thread each,
with a 90-second external limit per initial replay and at most eight recordings
per batch. Review smoke outcomes and source/model compatibility before expanding.
No automatic long campaign or silent budget increase. Large artifacts and test
temporary files use /home/mouse9911/.cache/leo/research/broad_prior_acquisition;
avoid writes to the stalled bulk filesystem or quota-limited /tmp.

Seal blind predictions before evaluator access to the roof reference. Preserve
failures, timeouts, unresolved map mass and prior-only controls. Report accepted
errors separately from diagnostic point errors, all-planned success fractions,
runtime including artifact work, and uncertainty/approximation diagnostics.
The coordinator owns shared I/O, orchestration and comparison; agents own
diagnostics, reduction and map implementations in separate files.
