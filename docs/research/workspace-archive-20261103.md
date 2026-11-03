# Historical workspace preservation, 2026-11-03

This branch preserves historical research files; it is not a production release.
Current development is published separately on `main` from the runtime worktree.

The November 3 supplemental archive captures 15,256 previously untracked
source/configuration/Markdown files under `reports/` and `docs/` that were
absent from both this branch and remote main. Their total source size is
93,753,907 bytes. This includes historical experimental variants and source
snapshots; archiving them does not endorse their scientific conclusions.

Selection included `.md`, `.py`, `.sh`, `.c`, `.h`, `.cpp`, `.toml`, `.yml`
and `.yaml` files. Build directories, work directories, virtual environments,
dependency caches and symlinks were excluded. Raw measurements, numerical
result dumps, logs, binaries and other generated experiment artifacts remain
on local research storage. Files already present on remote main were not
duplicated into this supplemental archive.

An obvious private-key/token pattern check found no matches. These historical
files were preserved without modifying or rerunning their experiments. They
have not been validated as a coherent runnable release. The current screened
detector checkpoint on main has its own tests and validation receipts.
