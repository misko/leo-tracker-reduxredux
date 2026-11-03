# Immutable catalogue index experiment

The optional `LEO_RESEARCH_WARM_ID_INDEX` session build replaces repeated linear
satellite-ID lookup with a sorted immutable index. It preserves original
catalogue order and first-match behavior for duplicate IDs. It does not change
which satellites are scored or the search budget. Default builds are unchanged.

On PLUTO+, a control/index/index/control sequence over the same 16 held-out
sites reduced mean CPU time from 10.5877435 to 10.521899 seconds (0.622%). All
scores matched exactly. The first control wall time includes unexplained
waiting; CPU time, not that wall-time difference, is the reported comparison.
This small experiment does not establish a sustained throughput improvement.

The full host search and associations also matched their previous controls
exactly. `comparison.json` contains the receipts; `protocol.json` pins the
benchmark payloads. The component test checks 22,001 lookups against linear
search, including duplicate and negative IDs, and checks an empty catalogue.

The combined `../fullchain-index-pgo-overlap-v1/` experiment additionally changes
the detector's GLRT archive to the previously trained PGO candidate. Its result
must not be attributed solely to this index.
