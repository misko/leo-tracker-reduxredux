# DS21-039 satellite-only temporal refresh sensitivity

Status: specified before execution; implementation and synthetic verification
are in progress. No position improvement is implied. The
[metadata audit](TEMPORAL_EVIDENCE.md) establishes potential revisit links, not
same-emitter continuity. This is an explicitly new model assumption.

The unchanged baseline treats the original 2,798 training windows independently.
The new condition carries only satellite-or-clutter state across selected
revisits. Native candidate/ambiguity choices are marginalized independently
within every window; ambiguity-slot identity is never carried across retunes.
The original native CFOs, receive times, candidate availability, RF values and
visibility masks remain exact. Satellite/clutter priors are not renormalized
after visibility masking.

For fixed original satellite/clutter prior `pi`, an elapsed receive-time gap
`dt` uses `T(dt) = rho I + (1-rho) 1*pi`, with `rho = exp(-dt / 1 second)`.
This permits direct switches between any satellite and clutter, and retains
`pi` as its stationary distribution. The one-second time constant is a
prespecified sensitivity assumption, not a fitted or independently measured
emitter persistence. It is not the existing sticky ambiguity-state graph,
whose signal-to-signal transitions require an observed intermediate clutter
state and whose stationary occupancy differs from its initial prior.

Families use receiver, channel, exact recorded RF and the original counter-based
20-second training partition block. Reset at gaps greater than one second,
non-increasing receive times, and every key change. The original observation
center supplies transition time; each candidate's own native GLRT center still
supplies its emission prediction. Original counter block and observation-center
block labels agree for all 2,798 windows; implementation must check that rather
than silently select a clock convention. The metadata inventory predicts 1,182
families and 1,616 edges: 227 singletons, 294 pairs and 661 triples. No held or
quarantined observation is added or used to bridge a family.

Both conditions fit common `c` with the original offsets, drifts, group
contrasts, orbital timing parameters and physical priors. Each gets the same
two physical initializers: the original all-band stationary winner and the
sealed seven-call refinement's selected free-position winner. Each of four
calls gets 20 seconds and 600 iterations, using the original seed-5 center and
25-km disk. The unchanged baseline may also retain either sealed stationary
source incumbent; the new condition must produce a new stationary fit.
There is no new zero-c arm, reference-derived seed or per-recording tuning.

Before fitting, the new emission/HMM arithmetic with singleton families must
reproduce both original states' objective, NLL, vector/nuisance gradients and
satellite/clutter/native probabilities. It may not bypass the new arithmetic
by dispatching to the baseline. Synthetic verification includes exact tiny-HMM
enumeration with unequal gaps and direct switches, stationary-prior closure,
missing candidates, changing visibility, all-signal-invisible windows, family
reset isolation, and full parameter finite differences with native timestamps
and the original group wrapper. The physical parameter layout and all prior
terms remain unchanged and are checked independently.

Freeze source bytes, inputs, prescribed starts, graph inventory and search
budgets before execution. Preserve every launch and outcome, including failures
and nonstationary fits, without silently retrying them. Select within each
condition by its own training objective and stationary status; do not compare
only whichever endpoint is closest to the reference. Join position errors only
after all outcomes and selections are sealed. Report frequency/NLL and prior
effects separately from position accuracy, including any association changes.

A successful frequency fit cannot validate emitter continuity or the 0.5-km
target. Any DS21-039 improvement remains a development result requiring the
other development cases and a frozen release before locked-set evaluation.
