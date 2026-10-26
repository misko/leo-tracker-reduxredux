# Pre-outcome support and timing clarification

2026-10-26 21:32 UTC, before new target outcomes in this branch. Parent protocol
SHA256: c019cb4a095dabaf318849da60128f0b948df7d34dd1e871d2529b39d4170289.

The independent gate requires the frozen confirmation rule; it does not require
both target groups independently to reproduce the original 20 ms detection
threshold as proof of physical presence. Splitting can lose weak-signal power.
The evaluation-only archived-timing oracle should therefore compare full-window,
search-group and confirmation-group availability on identical samples. Oracle
timing never selects operational predictions or discoveries. If full-window
oracle support survives while split confirmation fails, report a power or
partition bottleneck separately from timing-prediction error.

The proposed interleaved native-frame partition is acceptable if disjointness
holds over the union of every tested timing/mode block, including fractional
interpolation guards. A guard-aware owner check should independently verify
every sampled index. The mode/timing is sealed on search frames before one
confirmation score. Report frame counts and match those counts in controls;
minimum-frame failures are explicit unavailable states.

Report CFO at an explicit shared reference counter, preferably the original
native target midpoint used by baseline observations. Rates must be propagated
consistently to all frame times. A donor rate used for dechirping is conditioning
and should be declared, but the returned residual frequency must be determined
by later samples rather than a donor-posterior penalty. This unchanged-scorer
research path is judged on its own known-truth and null controls.

A full-window timing-selected score using the search samples again is not an
independent confirmation. It can still be an exploratory sensitivity diagnostic
when labeled and when the entire selection policy is repeated on matched nulls.
It cannot silently replace a failed frozen confirmation gate in this round.

The practical conditional-null screen in PROTOCOL.md is measurable with 32 or
more independent vectors per exposure stratum. Report trial uncertainty and
expected false confirmations at panel exposure; do not require an unreachable
panel family-wise bound to inspect whether coherent tracks can be recovered.
