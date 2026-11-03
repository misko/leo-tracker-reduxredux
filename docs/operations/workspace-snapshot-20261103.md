# Historical development workspace snapshot, 2026-11-03

This branch preserves the source, tests, documentation, deployment recipes, and
mechanical designs present in the original development checkout on November 3.
It is an archive of work in progress, not a production release or a proposal to
replace the current main branch.

The starting revision is `e9b28612abc5163328553cafcf7f8242d96b58b4` on
`codex/analysis-lane-sampling`. That history diverges from current main; some of
these files have newer implementations on main. This snapshot deliberately
retains the original contents without resolving that divergence.

The snapshot includes all 15 modified tracked files and regular untracked files
from `src`, `tests`, `tools`, `docs`, `scripts`, `.agents`, `3d_prints`, `deploy`,
and `web`, excluding generated logs, compiled extensions, build output, and
external linked directories. The accompanying
[source manifest](workspace-snapshot-20261103.json) records the selected files,
their sizes, and SHA-256 hashes before committing.

Research run directories, raw recordings, generated caches, external literature
collections, and local build environments remain in their existing storage.
This is not a complete backup of those data. No QNAP path was modified.

Validation for this archival operation checks content preservation and checks
for credential patterns. It does not claim that the historical workspace builds
or passes the current production test suite. Component changes require review
and their relevant tests before any future integration into main.
