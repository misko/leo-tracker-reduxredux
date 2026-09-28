# DS8: recordings after DS7

Frozen inventory cutoff: **2026-09-28 00:22:59 UTC**. The sealed
`manifest.json` admits 65 complete recordings, 143,988 visits and
590,315,544,389 compressed bytes. Sample rates: thirteen at 10 MS/s, fifteen
at 7.5 MS/s, seventeen at 5 MS/s and twenty at 2.5 MS/s.

Membership requires capture strictly after DS7, publication finalized by the
cutoff, complete visit/chunk accounting, qualified UTC and successful terminal
status. Analysis readiness is not an admission criterion. All 65 inventory
candidates passed. The manifest binds the parent DS7 manifest and each source
manifest. All 65 capture pose companions were verified and copied into `pose/`.
`SHA256SUMS` seals membership and pose files.

IQ remains in its existing source storage, accessed through the public read-only
reader. This is a membership snapshot, not a payload backup or retention hold.
Minting verified sealed metadata and chunk accounting; it did not rehash the
590 GB of compressed IQ. Read excerpts are verified by the source reader.
Raw excerpts and numerical results belong in ignored `local/` directories.
No new RF collection was requested or performed.

DS7 and DS8 have disjoint session IDs and source manifest digests. Together they
contain 153 recordings from the same roof receiver site. See the
[joint correspondence study](../2026_09_28_ds7_ds8_correspondence/README.md)
for decoding and repeat-satellite comparisons.

`mint.py` records the admission procedure and refuses to overwrite a sealed
manifest. `verify.py` verifies the offline seals, counts, pose bindings and
parent disjointness without accessing raw IQ.
