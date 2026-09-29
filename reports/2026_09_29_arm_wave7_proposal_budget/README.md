# Wave 7 approximate proposal-frame budgets

These variants start from sealed Wave6 combined and alter proposal formation
only. Budget 8 uses original frame indices `0,2,4,6,9,11,13,15`; budget 4 uses
`0,5,10,15`. Each lag's support is recomputed from its selected frames and its
own valid tail, before the existing normalization. The full downstream coarse,
conditioned, and final FP64 GLRT paths remain unchanged.

This is approximate candidate selection, not an exact optimization. Builds,
all-rate zero/extreme/tail support units, host32 gates, host704 frozen audits,
and matched-hit identity comparisons are recorded separately per budget. ARM
execution is owned by the root agent.

On the 32-dwell gate, Wave6 combined recovered 921/948 reference-positive
hits. Budget 8 recovered 906/948 (15 fewer); budget 4 recovered 801/948 (120
fewer) and was not expanded. Budget 8 host704 recovered 18,983/19,581, versus
19,217 for Wave6 combined. Its frozen identity comparison has 244 lost and 10
gained matched reference-hit identities; the net 234 agrees with the aggregate
recovery change. This does not qualify it as a quality-preserving reduction.
`proposal-budget8-identity-qualification.json` records counts by rate and
confirms all emitted JSON numeric fields were finite.
