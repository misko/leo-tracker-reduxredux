# DS3/DS4 positioning iteration 1

This iteration tests whether independent scan errors cancel before building a
new causal state cache for DS4. It consumes the sealed, truth-blind Sacramento
250 km result already produced for every DS3 and DS4 scan by
`scanner-adaptive-tle-position-v2`.

The six aggregation rules were fixed before post-seal evaluation: equal
spherical mean, inverse-RF-RMS-squared mean, lowest-RF-RMS 75% mean, closest
spatial 75% mean, spatial geometric median, and a Huber center whose cutoff is
1.5 times the current median spatial distance. Every complete scan contributes
at most one position. Eight-scan groups are chronological and non-overlapping;
the full scope uses every admitted scan. DS4's three-session remainder enters
the full scope and is not called an eight-scan group.

Neither extraction nor inference contains the surveyed coordinate. The
reference is introduced only by the separately sealed `postseal` command.
These are aggregation experiments over prior single-scan association results,
not a new joint satellite-association fit.
