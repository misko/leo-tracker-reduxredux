# Orbit timestamp audit for a possible causal freshness change

**Collection timestamps alone do not establish availability.** The collector
assigns the archived timestamp before its network fetch and writes/fsyncs the
snapshot afterward. The precise rationale for the 505second margin was not
found. Removing it requires independent completion evidence before capture;
the counts below are timestamp-screened candidates, not proven causal inputs.

The existing exporter selects snapshots strictly before `scan_start - 505s`,
then chooses the newest element per object among the latest provider snapshots.
This metadata audit separates two possible freshness gaps without propagating
orbits or fitting positions.

| Alternative availability rule | Changed candidate occasions / 3071 | Newer epochs | Scans with changes |
|---|---:|---:|---:|
| Retain best elements from preceding three days, same 505s guard |0|0|0|
| Same history, snapshot request timestamps before scan start |369|21|5|

There is no evidence of a provider rollback losing fresher historical elements
in this three-day window. Removing the 505s guard changes bytes on original
indices 10,13,16,27,31. A separate parsed-SGP4 audit finds only 96 changed
parameter sets: 75 differ solely by an eccentricity increment of 1e-7, and
21 have newer epochs. Byte changes must not be treated as equivalent to useful
orbital updates. Their request timestamps do not prove download completion.

The single newer-epoch candidate on index10 is not a training-MAP identity in
the prior CFO audit. On index31, two of the twenty updated candidate identities
are conditional training-MAP choices, spanning eight tracks and 220 training
observations. This is a possible narrowly scoped causal freshness test, not
evidence of lower position error. The reason for the 505s guard and the relevant
time authority must be established before changing the availability rule.

[inventory.json](inventory.json) records every selected snapshot/element and
strict cutoff. [semantic_audit.json](semantic_audit.json) compares epoch,
drag and orbital-element inputs through the SGP4 parser. Both scripts retain
source bindings, verify original element digests, and write exclusively.
No RF, archive writes, propagation, reference errors or position fits occur.
