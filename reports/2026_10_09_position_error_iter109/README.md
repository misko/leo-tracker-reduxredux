# Preserve label priors before testing temporal persistence

This is mathematical preparation and synthetic testing, not a positioning
experiment. No recording was evaluated with positive persistence, no persistence
strength was selected, and no accuracy improvement is claimed. The separately
frozen iteration108 descriptive census remains unchanged and is still running.

The original prototype always redraws clutter while retaining satellite labels.
Using the original row prior for every redraw consequently changes the marginal
satellite/clutter preference. A later score change could then reflect that
preference change as well as temporal dependence. We derived a linear-cost
transition that preserves the prescribed prior at every row, including visibility
changes, so those effects can be separated.

For previous/current priors p and q, retained satellite mass is
`h = rho * min(p, q)`, with clutter retained mass zero. Set `s = h/p` where p is
positive, otherwise zero, and `r = (q-h)/(1-sum(h))`. The transition is
`T = diag(s) + (1-s) rᵀ`. It satisfies `p T = q`; at rho0 it recovers the
independent mixture. The forward/backward computation remains O(K) per row.
It preserves priors, not posteriors: measured evidence can still propagate
between linked observations.

[The derivation](MARGINAL_PERSISTENCE.md), [integration review](PERSISTENCE_INTEGRATION_REVIEW.md)
and [independent kernel review](KERNEL_REVIEW.md) document the assumptions.
Eight synthetic tests pass, including changing visibility, new/disappearing
states, clutter, exhaustive sequence enumeration, emission gradients and the
complete detection-normalized independent limit. These do not replace future
composed physical/clock derivative, c=0 lock, extreme-probability and memory
checks. Rho remains a per-row retention parameter, not a measured physical
coherence time. No recording protocol for this model is frozen.

The [separate prior fusion audit](PRIOR_FUSION_AUDIT.md) preserves older batch
multi-scan results and their limitations; it is not a proposal to replace the
standalone accuracy goal with a warmed-up sequential metric.

The next recording decision depends on the complete iteration108 ambiguity
census. The full193 retained-region recovery comparison also remains pending
beyond its first four checks. Production B7, RF collection and reserves are
unchanged. The0.4 km mean-error objective remains unachieved.
