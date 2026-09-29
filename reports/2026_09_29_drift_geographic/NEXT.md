# Next candidate: uncertain shared-satellite assignments across receivers

The completed frequency-coherence census supplies training-selected one-to-one
RX pairs. Differential-drift corrections address a nuisance parameter; they do
not add a shared satellite trajectory to the position model. That remaining
constraint is the next direction to test now that all declared drift arms are
complete without a reliable sub-km result.
Do not expand drift bounds or select correction allocations using roof error.

Begin with a bounded support census on the same 72 scans, not new fits. For every
published selected pair, inspect whether its two retained satellite banks share
any catalogue rows under the same pinned snapshot. Stored candidate IDs are row
indices, not NORAD IDs. Equality is meaningful only within a verified identical
catalogue namespace. Cross-scan comparisons require an explicit identity map;
do not infer identity from matching integer indices across snapshots.

Keep all pairs, including empty intersections and missing bank-eligible tracks.
Report unweighted intersection sizes and the independent training posterior's
mass on matching identities, with both denominators explicit. Candidate agreement
is secondary model support, not an independent observation or identity truth.
Inspect whether support survives held frequency prediction before geographic
coupling. Use the cached banks and existing posterior artifacts; a namespace
check within a scan does not require new propagation or archive reads.

A subsequent model should compare independent assignments with an uncertain
shared-identity alternative. Keep one trajectory for both RXs only inside that
alternative, and preserve unmatched/background explanations and every original
observation. Normalize both assignment alternatives, account for receiver noise
dependence, and integrate or explicitly qualify relative-offset uncertainty.
Do not create extra independent observations by duplicating the shared signal.

Require exact zero-coupling replay, receiver-swap symmetry, held isolation,
synthetic correct/wrong-pair cases and an empty-intersection fallback. Freeze
coupling choices before scoring; report all declared choices rather than choosing
the closest coordinate. A shared identity can then make the scan-wide cone and
reception-order constraints meaningful, but only with explicit observing
opportunities and uncertain beam pose. No shared-identity geographic model or
new sub-km result has been executed in this report.
