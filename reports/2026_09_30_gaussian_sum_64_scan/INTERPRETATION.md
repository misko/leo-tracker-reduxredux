# Interpretation and next experiment

The primary question is whether this particular bounded Gaussian-sum tracker
can acquire a location from the standard Sacramento search region using one
recording. It is not a test of all mixture filters, and a stopped fit does not
show that the underlying RF measurements contain no location information.
Final counts and accuracy summaries belong to `evaluation.json` and `README.md`.

The 32 initial spatial cells are already a coarse approximation to a uniform
250 km disk. A new ambiguous track branches every spatial cell over satellite
identity and background. Keeping only the 32 heaviest children can discard
substantial probability before later tracks have a chance to disambiguate the
location. The explicit one-percent mass-loss gate makes this failure visible.
Increasing the component count without measuring approximation error would not
establish that acquisition is reliable.

Support failures have a different meaning. The frozen implementation rejects
an entire fit if any retained component crosses its spatial or height support;
the violating component may carry little probability. Its interpolator also
requires a supported four-knot stencil when shared clock and satellite epoch
states move. Those are conservative operational limits, not measurements of
position error. Failure reasons can overlap within a single stopped update.

The greedy arm deliberately collapses association uncertainty. A completed
greedy fit can still select a wrong satellite/location mode; completion is not
satellite-identity truth or calibrated confidence. Its discarded mass is
diagnostic and is not subject to the Gaussian-sum-only one-percent gate.

For a follow-on prototype, retain a broad acquisition representation before
switching to local Gaussians. An adaptive spatial grid or weighted particles
can keep multiple location modes, with whole-track satellite identities summed
out at each location and shared clock/drift uncertainty retained. Transfer to
local Gaussian components only when nonlinear-likelihood and probability-mass
checks demonstrate that the surviving regions are represented adequately.
Compare this with probability-preserving mixture reduction; use a small grid
oracle to measure approximation loss rather than merely raising the cap.

Before that experiment, independently validate the background likelihood and
the clock/orbit-error model. The current background slope prior is narrow
relative to some observed physical slopes, so numerical weight concentration
alone is not evidence of calibrated association confidence. Freeze revised
settings using separate development evidence, then evaluate a newly declared
panel; this 64-scan evaluation must remain unchanged.

The repeated roof recordings reset inference state and have distinct session
identities, but share a site, hardware and environmental errors. They do not
provide independent-site coverage calibration. The operator-supplied roof
coordinate is unsurveyed. Historical standard-pipeline selected points are
useful context, but their different tracks, objective, and incomplete search
budget prevent a matched accuracy claim.
