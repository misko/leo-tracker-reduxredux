# Identity persistence: synthetic preparation only

The final B7 likelihood assigns satellite/clutter probabilities independently
per observation. This prototype tests a simple O(NK) forward/backward model that
can softly retain identity along an existing measured track, while allowing
changes and clutter. It adds an assumption, not a new measurement. No position
improvement has been demonstrated and no recording experiment has run here.

The kernel preserves the complete independent B7 likelihood at zero persistence,
including its detection normalization. Twenty synthetic tests pass: six kernel
tests and fourteen segment-adapter tests. The latter pack every observation once,
permit links only within the same receiver/channel/exact RF and positive gaps of
at most two seconds, and leave overlapping or uncovered rows independent.
Removing an overlap breaks continuity rather than inventing a bridge.

[Mathematical specification](INDEPENDENT_LIMIT.md),
[source audit and proposed experiment](PREPARATION.md),
[author cross-check](REVIEW.md), and [independent review](INDEPENDENT_REVIEW.md)
describe the assumptions and limits. In particular, persistence is per window,
not a measured physical coherence time; clutter reset can change marginal label
preferences, and sequence memory still depends on segment length.

Next: freeze a no-fit coverage and assignment-ambiguity census using existing
bootstrap memberships at ordinary B7 endpoints, with both c arms and exact
independent-objective parity. Establish whether enough ambiguous linked evidence
exists before choosing a global persistence value or running position fits.
Composed physical/clock derivative checks and c=0 locks are still required.
No reference-guided segmentation, new RF, reserve access or deployment is part
of this preparation. All existing development recordings remain consumed.
