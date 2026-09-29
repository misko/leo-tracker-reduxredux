# Cross-snapshot physical catalogue identity and full-corpus recurrence

Freeze the full-ready authority and exact 258 DS7/DS8/DS9 input artifacts. Verify
all observation/bank bytes before execution. Resolve each exact baseline snapshot
digest through the read-only TleArchiveReader; never construct archive paths.
Reproduce the exporter's STARLINK DEB exclusion and parser ordering. Require
catalogue size, unique numbers, and agreement between the two public parsers.
Persist raw snapshots compressed losslessly, explicit row-to-number rosters,
and imported runtime source copies/digests. Unknown mappings fail closed.

No satellite states are propagated. Catalogue number equality identifies a
candidate object, not the origin of an observed signal. Element revisions and
orbital errors are not assumed constant across snapshots.

Primary full-corpus census uses raw bank membership, without pretending that
unfitted tracks have posterior weights. Count support from at least two distinct
strictly earlier scans, with all receivers/RFs allowed. Also report support
outside the target's deterministic chronological blocks of eight within each
dataset (the last block may be shorter). These full-corpus blocks differ from
some of the previously selected early/middle/late panels; label them separately.

Secondary comparison retains exactly the previous 72 scans and their original
eight-scan q020 training candidate distributions. Map row identities to catalogue
numbers, then repeat strong support from two earlier scans and from two earlier
scans outside the target's original panel. Strong donor membership requires
signal responsibility times conditional candidate weight >=0.5. Report target
conditional mass with zeros retained. Do not use full-pool weights from other
likelihoods. No held outcome or reference error selects mappings or support.

Four prelaunch tests cover roster reordering, size/uniqueness failures, invalid
indices, strict chronology and recording/block isolation. A single child has a
120-second limit, AS4GiB, BLAS1/nice19 and >=5GiB available memory. No retries,
new RF, IQ, provider fetches, propagation, QNAP mutation or production changes.
No correction or geographic accuracy result is produced. Recurrence is a
coverage prerequisite, not independent satellite identity or calibration.
