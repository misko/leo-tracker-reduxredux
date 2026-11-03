# DS11 has complete causal older-orbit support for the two pilot scans

The archive supplies changed older elements for every physical candidate in
both original pilot banks, using the exact24hour revision convention of the
historical uncertainty test. No newer/offline elements are substituted.

| Scan | Physical candidates | Older records available | Changed records | Joint groups | Grouped tracks | Singleton tracks | Common-candidate hypotheses across groups |
|---|---:|---:|---:|---:|---:|---:|---:|
|0|102|102|102|14|52|10|104|
|16|92|92|92|18|53|5|153|

For each scan, select the latest Space-Track occurrence strictly before capture
minus505seconds, then the last Space-Track occurrence at or before24hours prior
to that occurrence. Compare these records with the actual original bank's
merged-provider elements. All original elements are checked against their
pinned digests and epochs. Changed element bytes alone do not prove nonzero
Doppler changes at every observation; that requires propagation.

Original archive occurrences are identified by digest, provider AND collection
time. An initial digest-only dictionary incorrectly selected a later occurrence
of identical bytes and failed a causal check before writing scientific output.
The initial source and failure record are preserved. The corrected version
matches the occurrence recorded by the existing source inventory. This is a
diagnostic provenance fix; it does not imply the original position banks used
future data. Output metadata records exact paths as well as content digests.

The existing frozen joint-source groups retain a mixture over each group's
common physical candidate set. Every original track occurs once, in a group or
as a singleton. This conditions on a shared source within a group and restricts
candidate combinations relative to independent tracks; it is not authenticated
satellite identity. A later uncertainty experiment must retain a matched
zero-revision joint-identity control alongside original IID, so gains are not
mistakenly attributed to orbit uncertainty when they arise from association
constraints. All14/18 selected group identities have changed older records.

Three tests pass for strict/inclusive cutoff rules, repeated-digest occurrence
selection, and candidate-set intersection accounting. The corrected inventory
completes in0.41seconds. Independent verification reselects the causal archive
occurrences, rereads all five through the public read-only archive port, checks
194 original/older candidate occasions and verifies track accounting. No orbit
states, observation values, reference coordinates, IQ or positions are computed.

Next propagate the older records on the unchanged timing/observation grids,
replay original states exactly, and retain all candidate slots. These state
arrays will support candidate-dependent revision directions throughout a
position fit rather than freezing Doppler corrections at a chosen position.
