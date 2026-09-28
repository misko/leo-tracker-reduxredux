# Two-group chronological DS7 coverage tranche

Select chronological `single-025` through `single-040`, exactly `group8-04`
and `group8-05`, before their predictions or scores. The starting contract is
the wave-5 final input with 32 ready captures, digest
`cfedef0e5601845665184f993123d30e3af2bc27edc87815f9ae709fc5b424b6`.
Preserve all 88 identities and all 32 previous ready records exactly.

## Bounded parallel preparation

Terra owns captures 025–032 under `inputs/group04/`; SOL owns captures 033–040
under `inputs/group05/`. Each uses the unchanged combined exporter and a
separate `.leo/ds7-wave6/group04/` or `group05/` bank root. Source access is
read-only. No raw IQ or RF collection is authorized.

At most two preparation processes may run concurrently, each with one
CPU/BLAS thread, nice 19 and an inherited 3 GiB address-space ceiling. Each
worker has a separate 1,200-second total wall deadline and a 240-second
per-recording deadline. Retain all failures, partial outputs and unattempted
members; never widen a running deadline or overwrite an attempt.

This changes execution concurrency, not scientific selection or parameters.
Observed preparation processes consumed roughly 0.7 GiB RSS and almost one
CPU, and wave 5 completed its eight-recording controller in 917.17 seconds.
The host preflight showed roughly 29 GiB available. Require at least 12 GiB
available before launching the pair. At most one DS7 fitter may run alongside
them. Do not start other scientific experiments during this preparation pair.

Each worker starts from the same valid unfrozen 32-ready index, freezes
progressive snapshots in its own directory, and validates bindings before
publishing. Root combines disjoint prepared rows when needed; neither worker
overwrites the other's index or the common starting contract.

## Scientific panel

Use the wave-4 validated batched arm with unchanged scientific configuration.
Each chronological group has a separate 900-adapter-second lease, including
its eight singles and one complete joint group fit; the per-unit cap is 300
seconds. Keep one fitting process, CPU/BLAS1 and nice19. Every single runs once.

SOL may independently validate published input snapshots and launch already
declared units without another per-recording dispatch from root: require all
88 identities/manifests, exact preservation of the starting 32 ready rows,
artifact hashes, code/config hashes, eligible-track coverage and timing-grid
checks. Publish those validations with each launch. Run a group only when its
complete eight-member input is ready. Root independently audits source seals
before scoring or aggregating.

Root runs the same three controls for each group, at most ten adapter seconds
per control, using all eight qualified source estimates and frozen training
RMS. Seal before reference scoring. Report all failures and missing members.

This tranche advances full88 coverage. Partial-group or selected-recording
success cannot close the full-DS7 goal.
